/* liftdiff native ランナ: PE x64 を preferred ImageBase に敷設し、関数 VA を MS x64 ABI で直接実行する。
 * stdin: 1 行プロトコル (LAYOUT/WR/SNAPSHOT/BLOB/FIX/TRACESET/CASE/QUIT)、stdout: 1 case 1 行 JSON。
 * 使い方: ld_native <pe-file>
 */
#define _GNU_SOURCE
#include "ld_core.h"
#include <signal.h>
#include <setjmp.h>
#include <ucontext.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#pragma pack(push,1)
typedef struct { uint16_t Machine, NumberOfSections; uint32_t TimeDateStamp, PtrSym, NumSym; uint16_t SizeOfOptionalHeader, Characteristics; } FILEHDR;
typedef struct { uint32_t VA, Size; } DDIR;
typedef struct { uint16_t Magic; uint8_t mj, mn; uint32_t SizeCode, SizeInit, SizeUninit, Entry, BaseCode; uint64_t ImageBase; uint32_t SecAlign, FileAlign;
  uint16_t a,b,c,d,e,f; uint32_t Win32Ver, SizeOfImage, SizeOfHeaders, Checksum; uint16_t Subsys, DllChar; uint64_t SR, SC, HR, HC; uint32_t LoaderFlags, NumDD; DDIR dd[16]; } OPT64;
typedef struct { char Name[8]; uint32_t VSize, VA, RawSize, RawPtr, r1, r2; uint16_t n1, n2; uint32_t Chars; } SEC;
typedef struct { uint32_t OFT, TDS, Fwd, Name, FT; } IMPDESC;
#pragma pack(pop)

extern void ld_ms_call(void* fn, const u64* gpr4, const u64* xmm4, const u64* stk, long nstk, u64* out4, u64 rax_init);
extern void ld_stub_common(void);

static u8* g_file; static size_t g_filesz;
static u64 g_imgbase, g_imgsize;
static u8* g_thunks;
#define MAX_IMP 4096
static char* g_impname[MAX_IMP];
static int g_nimp;

u64 ld_stub_c(u64 idx, u64 a0, u64 a1, u64 a2, u64 a3, const u64* stk) {
  const char* n = "?bad";
  if (idx >= LD_FAKEPROC_MARK) n = ld_fakeproc_name(idx - LD_FAKEPROC_MARK);   /* GetProcAddress 仮 proc */
  else if (idx < (u64)g_nimp) n = g_impname[idx];
  u64 a4 = 0, a5 = 0;                                 /* 既定 0 */
  if (stk && (strcmp(n, "MultiByteToWideChar") == 0 || strcmp(n, "WideCharToMultiByte") == 0)) {
    a4 = stk[0]; a5 = stk[1];                          /* MS 第5/6引数 (6引数 API のみ読む) */
  }
  return ld_stub(n, a0, a1, a2, a3, a4, a5);
}

/* CAB-233: 仮 proc の実行可能 thunk (LD_FAKEPROC_BASE 固定番地 = wasm 側の値と同一)。
 * thunk: mov r10, LD_FAKEPROC_MARK|i ; mov r11, ld_stub_common ; jmp r11 */
static u8* g_fake_thunks;
u64 ld_fake_ptr(u64 i) {
  if (i >= 32768) return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ;
  if (!g_fake_thunks) {
    g_fake_thunks = mmap((void*)(uintptr_t)LD_FAKEPROC_BASE, 1 << 20, PROT_READ | PROT_WRITE | PROT_EXEC,
                         MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (g_fake_thunks != (void*)(uintptr_t)LD_FAKEPROC_BASE) {
      fprintf(stderr, "[ld_native] fakeproc page mmap failed (calls into fake procs will fault)\n");
      g_fake_thunks = (u8*)-1;
      return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ;
    }
  }
  if (g_fake_thunks == (u8*)-1) return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ;
  u8* p = g_fake_thunks + (size_t)i * LD_FAKEPROC_SZ;
  if (p[0] != 0x49) {   /* 未生成 */
    u64 im = LD_FAKEPROC_MARK | i, cm = (u64)(uintptr_t)ld_stub_common;
    p[0] = 0x49; p[1] = 0xBA; memcpy(p + 2, &im, 8);
    p[10] = 0x49; p[11] = 0xBB; memcpy(p + 12, &cm, 8);
    p[20] = 0x41; p[21] = 0xFF; p[22] = 0xE3;
  }
  return (u64)(uintptr_t)p;
}

static int load_pe(const char* path) {
  FILE* f = fopen(path, "rb"); if (!f) { perror(path); return -1; }
  fseek(f, 0, SEEK_END); g_filesz = (size_t)ftell(f); fseek(f, 0, SEEK_SET);
  g_file = malloc(g_filesz); if (fread(g_file, 1, g_filesz, f) != g_filesz) return -1; fclose(f);
  uint32_t pe; memcpy(&pe, g_file + 0x3c, 4);
  FILEHDR* fh = (FILEHDR*)(g_file + pe + 4); OPT64* oh = (OPT64*)(g_file + pe + 4 + sizeof(FILEHDR));
  if (fh->Machine != 0x8664) { fprintf(stderr, "not x64 PE\n"); return -1; }
  g_imgbase = oh->ImageBase; g_imgsize = oh->SizeOfImage;
  void* m = mmap((void*)g_imgbase, g_imgsize, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
  if (m != (void*)g_imgbase) { fprintf(stderr, "mmap image at %#llx failed\n", (unsigned long long)g_imgbase); return -1; }
  ld_img = (u8*)g_imgbase;
  memcpy(ld_img, g_file, oh->SizeOfHeaders);
  SEC* sec = (SEC*)((u8*)oh + fh->SizeOfOptionalHeader);
  for (int i = 0; i < fh->NumberOfSections; i++) {
    u32 n = sec[i].RawSize < sec[i].VSize ? sec[i].RawSize : sec[i].VSize;
    if (!sec[i].VSize) n = sec[i].RawSize;
    if (sec[i].RawPtr + n <= g_filesz) memcpy(ld_img + sec[i].VA, g_file + sec[i].RawPtr, n);
  }
  g_thunks = mmap(NULL, 1 << 20, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  u32 iva = oh->dd[1].VA;
  int nimp = 0;
  if (iva) {
    for (IMPDESC* d = (IMPDESC*)(ld_img + iva); d->Name || d->FT; d++) {
      const char* dll = (const char*)(ld_img + d->Name);
      u64* oft = (u64*)(ld_img + (d->OFT ? d->OFT : d->FT)); u64* ft = (u64*)(ld_img + d->FT);
      for (int k = 0; oft[k]; k++) {
        char nm[256];
        if (oft[k] >> 63) snprintf(nm, sizeof nm, "%s!ord%u", dll, (unsigned)(oft[k] & 0xffff));
        else snprintf(nm, sizeof nm, "%s", (const char*)(ld_img + (oft[k] & 0x7fffffff) + 2));
        if (g_nimp >= MAX_IMP) { fprintf(stderr, "too many imports\n"); return -1; }
        int idx = g_nimp++; g_impname[idx] = strdup(nm);
        u8* p = g_thunks + (size_t)idx * 32; u64 im = (u64)idx, cm = (u64)(uintptr_t)ld_stub_common;
        p[0] = 0x49; p[1] = 0xBA; memcpy(p + 2, &im, 8);     /* mov r10, idx */
        p[10] = 0x49; p[11] = 0xBB; memcpy(p + 12, &cm, 8);  /* mov r11, common */
        p[20] = 0x41; p[21] = 0xFF; p[22] = 0xE3;            /* jmp r11 */
        ft[k] = (u64)(uintptr_t)p; nimp++;
      }
    }
  }
  fprintf(stderr, "[ld_native] image %#llx size %#llx, imports %d\n", (unsigned long long)g_imgbase, (unsigned long long)g_imgsize, nimp);
  return 0;
}

/* ---------------- シグナル ---------------- */
static sigjmp_buf g_jb;
static volatile int g_in_call;
static volatile int g_sig; static volatile u64 g_fault_addr, g_fault_rip;
static volatile u64 g_fault_rsp; static volatile u64 g_fault_stk[256];  /* fault 時の rsp と stack 語 (guest 呼出し site 復元用) */
static volatile u64 g_fault_g[16];   /* CAB-233: fault 時の汎用レジスタ (rbp/rbx/rdi/rsi/rax/rcx/rdx は仮想 call 後のフレーム破壊診断用) */
static u64 *g_tr_va; static u8* g_tr_orig; static int g_ntr_set;
static u8* volatile g_pending;

static int tr_find(u64 addr) {
  int lo = 0, hi = g_ntr_set - 1;
  while (lo <= hi) { int m = (lo + hi) >> 1; if (g_tr_va[m] == addr) return m; if (g_tr_va[m] < addr) lo = m + 1; else hi = m - 1; }
  return -1;
}
static void tr_arm(void) { for (int i = 0; i < g_ntr_set; i++) *(u8*)g_tr_va[i] = 0xCC; }
static void tr_disarm(void) { for (int i = 0; i < g_ntr_set; i++) *(u8*)g_tr_va[i] = g_tr_orig[i]; g_pending = NULL; }

/* 命令単位の trace (LD-57 / #1636): env LD_STEP_N=<上限>・LD_STEP_OUT=<接頭辞> で有効。
 * case の関数 entry に int3 を置き、そこから TF (single-step) で image 内の命令を 1 つずつ記録する。
 * 出力: <接頭辞>.<case id> に 1 行 1 命令 (rva と主要レジスタ, 16 進)。既定 (env 未設定) は無効。 */
static u64 g_step_entry, g_step_max, g_step_cnt; static u8 g_step_orig; static int g_step_armed, g_step_on; static FILE* g_step_fp;
static void step_rec(greg_t* g) {
  if (!g_in_call || g_step_cnt >= g_step_max) { g[REG_EFL] &= ~0x100; g_step_on = 0; return; }
  u64 rip = (u64)g[REG_RIP];
  if (rip >= g_imgbase && rip < g_imgbase + g_imgsize) {
    fprintf(g_step_fp, "%llx %llx %llx %llx %llx %llx %llx %llx %llx %llx %llx\n", (unsigned long long)(rip - g_imgbase),
            (unsigned long long)g[REG_RAX], (unsigned long long)g[REG_RCX], (unsigned long long)g[REG_RDX], (unsigned long long)g[REG_RBX],
            (unsigned long long)g[REG_RSP], (unsigned long long)g[REG_RBP], (unsigned long long)g[REG_RSI], (unsigned long long)g[REG_RDI],
            (unsigned long long)g[REG_R8], (unsigned long long)g[REG_R9]);
    g_step_cnt++;
  }
  g[REG_EFL] |= 0x100;
}
static void step_begin(void) {
  g_step_max = 0; g_step_cnt = 0; g_step_on = 0; g_step_armed = 0; g_step_fp = NULL;
  const char* n = getenv("LD_STEP_N"); const char* o = getenv("LD_STEP_OUT");
  if (!n || !o || !atoll(n)) return;
  char path[512]; snprintf(path, sizeof path, "%s.%s", o, ld_case.id);
  g_step_fp = fopen(path, "w"); if (!g_step_fp) return;
  g_step_max = (u64)atoll(n); g_step_entry = ld_case.fn; g_step_orig = *(u8*)(uintptr_t)ld_case.fn; g_step_armed = 1;
  *(u8*)(uintptr_t)ld_case.fn = 0xCC;
}
static void step_end(void) {
  if (g_step_armed) { *(u8*)(uintptr_t)g_step_entry = g_step_orig; g_step_armed = 0; }
  g_step_on = 0; g_step_max = 0;
  if (g_step_fp) { fclose(g_step_fp); g_step_fp = NULL; }
}

static void on_sig(int sig, siginfo_t* si, void* ucv) {
  ucontext_t* uc = (ucontext_t*)ucv; greg_t* g = uc->uc_mcontext.gregs;
  if (sig == SIGTRAP && g_step_on) { step_rec(g); return; }
  if (sig == SIGTRAP && g_in_call && g_step_armed && (u64)g[REG_RIP] - 1 == g_step_entry) {
    *(u8*)(uintptr_t)g_step_entry = g_step_orig; g_step_armed = 0; g[REG_RIP] = (greg_t)g_step_entry; g_step_on = 1;
    step_rec(g); return;
  }
  if (sig == SIGTRAP && g_in_call) {
    if (g_pending) { *g_pending = 0xCC; g_pending = NULL; g[REG_EFL] &= ~0x100; return; }
    u64 addr = (u64)g[REG_RIP] - 1; int k = tr_find(addr);
    if (k >= 0) {
      u64 a[8] = {0}, x[4] = {0};
      a[0] = g[REG_RCX]; a[1] = g[REG_RDX]; a[2] = g[REG_R8]; a[3] = g[REG_R9];
      u64* sp = (u64*)g[REG_RSP]; for (int j = 0; j < 4; j++) a[4 + j] = sp[5 + j];   /* [rsp]=ret, +8..+0x20 shadow, +0x28 = 5th */
      for (int j = 0; j < 4; j++) x[j] = uc->uc_mcontext.fpregs->_xmm[j].element[0] | ((u64)uc->uc_mcontext.fpregs->_xmm[j].element[1] << 32);
      ld_trace_rec((u64)addr, 0, a, x);
      if (ld_ntr >= LD_MAX_TR) { tr_disarm(); g[REG_RIP] = (greg_t)addr; return; }
      *(u8*)addr = g_tr_orig[k]; g[REG_RIP] = (greg_t)addr; g[REG_EFL] |= 0x100; g_pending = (u8*)addr;
      return;
    }
  }
  if (g_in_call) {
    g_sig = sig; g_fault_addr = (u64)(uintptr_t)si->si_addr; g_fault_rip = (u64)g[REG_RIP];
    g_fault_rsp = (u64)g[REG_RSP];
    { static const int rg[8] = {REG_RBP, REG_RBX, REG_RDI, REG_RSI, REG_RAX, REG_RCX, REG_RDX, REG_R8};
      for (int j = 0; j < 8; j++) g_fault_g[j] = (u64)g[rg[j]]; }
    u64* sp = (u64*)g_fault_rsp;
    for (int j = 0; j < 64; j++) g_fault_stk[j] = sp[j];   /* デバッグ用: fault 時の stack 上位語 */
    g[REG_EFL] &= ~0x100;
    siglongjmp(g_jb, 1);
  }
  _exit(98);
}
static void install_signals(void) {
  static u8 altstk[1 << 16];
  stack_t ss = { .ss_sp = altstk, .ss_size = sizeof altstk, .ss_flags = 0 }; sigaltstack(&ss, NULL);
  struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = on_sig; sa.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_NODEFER; sigemptyset(&sa.sa_mask);
  int sigs[] = { SIGSEGV, SIGBUS, SIGILL, SIGFPE, SIGTRAP, SIGALRM, SIGABRT };
  for (unsigned i = 0; i < sizeof sigs / sizeof *sigs; i++) sigaction(sigs[i], &sa, NULL);
}

static const char* signame(int s) {
  switch (s) { case SIGSEGV: return "segv"; case SIGBUS: return "bus"; case SIGILL: return "sigill"; case SIGFPE: return "sigfpe";
    case SIGTRAP: return "sigtrap"; case SIGALRM: return "timeout"; case SIGABRT: return "abort"; default: return "signal"; }
}

static void __attribute__((noinline)) scrub_stack(int fill) {
  volatile u8 b[1 << 17];
  memset((void*)b, fill, sizeof b);
  __asm__ volatile("" : : "r"(b) : "memory");
}

static void run_case(char* line) {
  ld_parse_case(line);
  ld_case_begin();
  u64 gpr[4] = {0}, xmm[4] = {0}, stk[16] = {0}; int nstk = 8;
  for (int i = 0; i < ld_case.nargs; i++) {
    char k = ld_case.kind[i]; u64 v = ld_case.val[i];
    if (i < 4) { if (k == 'i') gpr[i] = v; else xmm[i] = v; }
    else { stk[i - 4] = v; if (i - 4 + 1 > nstk) nstk = i - 4 + 1; }
  }
  if (ld_case.xfill) {   /* wasm の署名に無い位置のレジスタにも決定的な値を入れる (引数脱落の検出用) */
    for (int i = 0; i < 4; i++) {
      int isint = (i >= ld_case.nargs) || ld_case.kind[i] == 'i';
      if (isint) { double d = 1.25 + i; memcpy(&xmm[i], &d, 8); }
      else if (i >= ld_case.nargs || 1) { if (gpr[i] == 0) gpr[i] = 0x11 + i; }
    }
  }
  u64 out[4] = {0};
  void* fn = (void*)(uintptr_t)ld_case.fn;
  if (ld_case.fn < g_imgbase || ld_case.fn >= g_imgbase + g_imgsize) {
    puts(ld_case_end("bad_fn", "fn outside image", 0, 0, 0, 0, 0, 0, 0)); fflush(stdout); return;
  }
  g_sig = 0; g_pending = NULL; g_fault_rsp = 0; g_fault_stk[0] = 0;
  for (int j = 0; j < 8; j++) g_fault_g[j] = 0;
  scrub_stack(ld_case.stkfill);
  step_begin();
  if (ld_case.trace && !g_step_max) tr_arm();
  struct itimerval it = { {0, 0}, {1, 500000} };
  struct timespec t0, t1;
  ld_native_ms = -1.0;
  if (sigsetjmp(g_jb, 1) == 0) {
    g_in_call = 1; setitimer(ITIMER_REAL, &it, NULL);
    clock_gettime(CLOCK_MONOTONIC, &t0);
    ld_ms_call(fn, gpr, xmm, stk, nstk, out, ld_case.rax);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    ld_native_ms = (double)(t1.tv_sec - t0.tv_sec) * 1e3 + (double)(t1.tv_nsec - t0.tv_nsec) / 1e6;
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    step_end();
    puts(ld_case_end("ok", NULL, 0, 0, out[0], out[1], out[2], out[3], 1));
  } else {
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    step_end();
    u64 rip = g_fault_rip;
    char det[512]; snprintf(det, sizeof det, "rip_rva=%#llx", (unsigned long long)(rip - g_imgbase));
    /* fault 時の stack 語を detail に加える (call 直後の [rsp] = 呼出し site の復元用) */
    { char* p = det + strlen(det); u64 rsp = g_fault_rsp;
      p += snprintf(p, sizeof det - (size_t)(p - det), " rsp=%#llx rbp=%#llx rbx=%#llx rdi=%#llx rsi=%#llx rax=%#llx rcx=%#llx rdx=%#llx r8=%#llx",
                    (unsigned long long)rsp, (unsigned long long)g_fault_g[0], (unsigned long long)g_fault_g[1],
                    (unsigned long long)g_fault_g[2], (unsigned long long)g_fault_g[3], (unsigned long long)g_fault_g[4],
                    (unsigned long long)g_fault_g[5], (unsigned long long)g_fault_g[6], (unsigned long long)g_fault_g[7]);
      for (int j = 0; j < 8; j++) p += snprintf(p, sizeof det - (size_t)(p - det), " s%d=%#llx", j, (unsigned long long)g_fault_stk[j]);
      /* guest 外 (host 領域) fault 時: stack を遡り最初の image 内 return address を探す (guest 呼出し site の復元) */
      if (rip < g_imgbase || rip >= g_imgbase + g_imgsize) {
        u64* sp2 = (u64*)g_fault_rsp;
        for (int j = 0; j < 4096; j++) {   /* host frame を遡り最初の guest (image 内) return address を探す */
          u64 v = sp2[j];
          if (v >= g_imgbase + 0x1000 && v < g_imgbase + g_imgsize && (v & 7) == 0) {
            p += snprintf(p, sizeof det - (size_t)(p - det), " gs_ret=%#llx", (unsigned long long)v);
            break;
          }
        }
      }
      (void)p; }
    puts(ld_case_end(signame(g_sig), det, g_fault_addr, rip, 0, 0, 0, 0, 0));
  }
  fflush(stdout);
}

static char* g_line; static size_t g_linecap;
int main(int argc, char** argv) {
  if (argc < 2) { fprintf(stderr, "usage: ld_native <pe>\n"); return 2; }
  setvbuf(stdout, NULL, _IOFBF, 1 << 20);
  if (load_pe(argv[1])) return 3;
  install_signals();
  while (getline(&g_line, &g_linecap, stdin) > 0) {
    char* l = g_line; size_t n = strlen(l); while (n && (l[n-1] == '\n' || l[n-1] == '\r')) l[--n] = 0;
    if (!strncmp(l, "LAYOUT ", 7)) {
      unsigned long long d, a, as, h, hs;
      if (sscanf(l + 7, "%llx %llx %llx %llx %llx", &d, &a, &as, &h, &hs) != 5) { fprintf(stderr, "bad LAYOUT\n"); return 4; }
      ld_delta = d; ld_arena_size = as; ld_heap_size = hs;
      ld_arena = mmap((void*)(a + d), as, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
      ld_heap = mmap((void*)(h + d), hs, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
      if (ld_arena != (void*)(a + d) || ld_heap != (void*)(h + d)) { fprintf(stderr, "mmap arena/heap failed\n"); return 5; }
      syscall(SYS_arch_prctl, 0x1001 /*ARCH_SET_GS*/, (unsigned long)(ld_heap + LD_TEB_OFF));
    } else if (!strncmp(l, "WR ", 3)) {
      unsigned long long r, len; if (sscanf(l + 3, "%llx %llx", &r, &len) == 2) ld_add_wr(r, len);
    } else if (!strcmp(l, "SNAPSHOT")) {
      ld_snapshot(); puts("{\"ready\":true}"); fflush(stdout);
    } else if (!strncmp(l, "BLOB ", 5)) {
      char* sp = strchr(l + 5, ' '); if (sp) { *sp = 0; ld_cmd_blob(l + 5, sp + 1); }
    } else if (!strncmp(l, "FIX ", 4)) {
      char* sp = strchr(l + 4, ' '); if (sp) { *sp = 0; ld_cmd_fix(l + 4, sp + 1); }
    } else if (!strncmp(l, "TRACESET ", 9)) {
      free(g_tr_va); free(g_tr_orig); g_ntr_set = 0;
      size_t cnt = 1; for (char* p = l + 9; *p; p++) if (*p == ',') cnt++;
      g_tr_va = malloc(cnt * 8); g_tr_orig = malloc(cnt);
      char* sv; for (char* t = strtok_r(l + 9, ",", &sv); t; t = strtok_r(NULL, ",", &sv)) {
        u64 v = strtoull(t, NULL, 16);
        if (v >= g_imgbase && v < g_imgbase + g_imgsize) g_tr_va[g_ntr_set++] = v;
      }
      for (int i = 1; i < g_ntr_set; i++) { u64 v = g_tr_va[i]; int j = i - 1; while (j >= 0 && g_tr_va[j] > v) { g_tr_va[j+1] = g_tr_va[j]; j--; } g_tr_va[j+1] = v; }
      for (int i = 0; i < g_ntr_set; i++) g_tr_orig[i] = *(u8*)g_tr_va[i];
    } else if (!strncmp(l, "CASE ", 5)) {
      run_case(l + 5);
    } else if (!strncmp(l, "PEEK ", 5)) {   /* PEEK <i:rva|a:off|h:off|hex> <n> */
      char tok[64]; int cnt = 0; if (sscanf(l + 5, "%63s %d", tok, &cnt) == 2) {
        u8* p = (u8*)(uintptr_t)ld_parse_val(tok); ld_ob_reset(); ld_hex(p, cnt); puts(ld_out); fflush(stdout); }
    } else if (!strncmp(l, "POKE ", 5)) {   /* POKE <i:rva|a:off|h:off> <hex>: 状態中の任意位置へ直接書込み (#2718) */
      char* sp = strchr(l + 5, ' ');
      if (sp) { *sp = 0; int n = ld_unhex(sp + 1, (u8*)(uintptr_t)ld_parse_val(l + 5), 1 << 16); printf("{\"poke\":%d}\n", n); fflush(stdout); }
    } else if (!strcmp(l, "STATE")) {
      puts(ld_state_dump()); fflush(stdout);
    } else if (l[0] == 'S' && (!strncmp(l, "SIMG ", 5) || !strncmp(l, "SHEAP ", 6) || !strncmp(l, "SMODEL ", 7) || !strcmp(l, "SSNAP"))) {
      char* a = strchr(l, ' '); char* b = NULL;
      if (a) { *a++ = 0; b = strchr(a, ' '); if (b) *b++ = 0; }
      ld_state_cmd(l, a ? a : "", b ? b : "");
    } else if (!strcmp(l, "QUIT")) break;
  }
  return 0;
}
