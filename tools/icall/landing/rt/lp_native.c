/* lp_native.c — landing pad 検証用ネイティブ ランナ (CAB-227, liftdiff ld_native.c 派生).
 *
 * ld_native.c との差は run_case の呼出し部のみ: pad は親関数の例外ハンドラ断片で
 * 「Rip 設定で進入する」ため、MS ABI trampoline の代わりに
 *   rbp := arg0 (親フレーム), 非live-inレジスタ := 0
 * で pad VA の実機械語を直接実行する (lp_call.S)。
 * プロトコル / 差分コアは tools/liftdiff/rt/ld_core.h を共有 (FORMAT.md 準拠出力)。
 */
#define _GNU_SOURCE
#include "ld_core.h"
#include <signal.h>
#include <setjmp.h>
#include <ucontext.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <unistd.h>

#pragma pack(push,1)
typedef struct { uint16_t Machine, NumberOfSections; uint32_t TimeDateStamp, PtrSym, NumSym; uint16_t SizeOfOptionalHeader, Characteristics; } FILEHDR;
typedef struct { uint32_t VA, Size; } DDIR;
typedef struct { uint16_t Magic; uint8_t mj, mn; uint32_t SizeCode, SizeInit, SizeUninit, Entry, BaseCode; uint64_t ImageBase; uint32_t SecAlign, FileAlign;
  uint16_t a,b,c,d,e,f; uint32_t Win32Ver, SizeOfImage, SizeOfHeaders, Checksum; uint16_t Subsys, DllChar; uint64_t SR, SC, HR, HC; uint32_t LoaderFlags, NumDD; DDIR dd[16]; } OPT64;
typedef struct { char Name[8]; uint32_t VSize, VA, RawSize, RawPtr, r1, r2; uint16_t n1, n2; uint32_t Chars; } SEC;
typedef struct { uint32_t OFT, TDS, Fwd, Name, FT; } IMPDESC_;
#pragma pack(pop)

extern void lp_call(void* fn, u64 rbp_val, const u64* gpr_in, u64* out);   /* lp_call.S */
extern void ld_stub_common(void);

static u8* g_file; static size_t g_filesz;
static u64 g_imgbase, g_imgsize;
static u8* g_thunks;
#define MAX_IMP 4096
static char* g_impname[MAX_IMP];
static int g_nimp;

u64 ld_stub_c(u64 idx, u64 a0, u64 a1, u64 a2, u64 a3) {
  const char* n = idx < (u64)g_nimp ? g_impname[idx] : "?bad";
  return ld_stub(n, a0, a1, a2, a3);
}

static int load_pe(const char* path) {
  FILE* f = fopen(path, "rb"); if (!f) { perror(path); return -1; }
  fseek(f, 0, SEEK_END); g_filesz = (size_t)ftell(f); fseek(f, 0, SEEK_SET); g_file = malloc(g_filesz);
  if (fread(g_file, 1, g_filesz, f) != g_filesz) return -1; fclose(f);
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
    for (IMPDESC_* d = (IMPDESC_*)(ld_img + iva); d->Name || d->FT; d++) {
      const char* dll = (const char*)(ld_img + d->Name);
      u64* oft = (u64*)(ld_img + (d->OFT ? d->OFT : d->FT)); u64* ft = (u64*)(ld_img + d->FT);
      for (int k = 0; oft[k]; k++) {
        char nm[256];
        if (oft[k] >> 63) snprintf(nm, sizeof nm, "%s!ord%u", dll, (unsigned)(oft[k] & 0xffff));
        else snprintf(nm, sizeof nm, "%s", (const char*)(ld_img + (oft[k] & 0x7fffffff) + 2));
        if (g_nimp >= MAX_IMP) { fprintf(stderr, "too many imports\n"); return -1; }
        int idx = g_nimp++; g_impname[idx] = strdup(nm);
        u8* p = g_thunks + (size_t)idx * 32; u64 im = (u64)idx, cm = (u64)(uintptr_t)ld_stub_common;
        p[0] = 0x49; p[1] = 0xBA; memcpy(p + 2, &im, 8);
        p[10] = 0x49; p[11] = 0xBB; memcpy(p + 12, &cm, 8);
        p[20] = 0x41; p[21] = 0xFF; p[22] = 0xE3;
        ft[k] = (u64)(uintptr_t)p; nimp++;
      }
    }
  }
  fprintf(stderr, "[lp_native] image %#llx size %#llx, imports %d\n", (unsigned long long)g_imgbase, (unsigned long long)g_imgsize, nimp);
  return 0;
}

/* ---------------- シグナル (ld_native.c と同一) ---------------- */
static sigjmp_buf g_jb;
static volatile int g_in_call;
static volatile int g_sig; static volatile u64 g_fault_addr, g_fault_rip;
static u64 *g_tr_va; static u8* g_tr_orig; static int g_ntr_set;
static u8* volatile g_pending;

static int tr_find(u64 addr) {
  int lo = 0, hi = g_ntr_set - 1;
  while (lo <= hi) { int m = (lo + hi) >> 1; if (g_tr_va[m] == addr) return m; if (g_tr_va[m] < addr) lo = m + 1; else hi = m - 1; }
  return -1;
}
static void tr_arm(void) { for (int i = 0; i < g_ntr_set; i++) *(u8*)g_tr_va[i] = 0xCC; }
static void tr_disarm(void) { for (int i = 0; i < g_ntr_set; i++) *(u8*)g_tr_va[i] = g_tr_orig[i]; g_pending = NULL; }

static void on_sig(int sig, siginfo_t* si, void* ucv) {
  ucontext_t* uc = (ucontext_t*)ucv; greg_t* g = uc->uc_mcontext.gregs;
  if (sig == SIGTRAP && g_in_call) {
    if (g_pending) { *g_pending = 0xCC; g_pending = NULL; g[REG_EFL] &= ~0x100; return; }
    u64 addr = (u64)g[REG_RIP] - 1; int k = tr_find(addr);
    if (k >= 0) {
      u64 a[8] = {0}, x[4] = {0};
      a[0] = g[REG_RCX]; a[1] = g[REG_RDX]; a[2] = g[REG_R8]; a[3] = g[REG_R9];
      u64* sp = (u64*)g[REG_RSP]; for (int j = 0; j < 4; j++) a[4 + j] = sp[5 + j];
      for (int j = 0; j < 4; j++) x[j] = uc->uc_mcontext.fpregs->_xmm[j].element[0] | ((u64)uc->uc_mcontext.fpregs->_xmm[j].element[1] << 32);
      ld_trace_rec((u64)addr, 0, a, x);
      if (ld_ntr >= LD_MAX_TR) { tr_disarm(); g[REG_RIP] = (greg_t)addr; return; }
      *(u8*)addr = g_tr_orig[k]; g[REG_RIP] = (greg_t)addr; g[REG_EFL] |= 0x100; g_pending = (u8*)addr;
      return;
    }
  }
  if (g_in_call) {
    g_sig = sig; g_fault_addr = (u64)(uintptr_t)si->si_addr; g_fault_rip = (u64)g[REG_RIP];
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

static void run_case(char* line) {
  ld_parse_case(line);
  ld_case_begin();
  /* args: arg0 = frame (rbp), arg1..4 = live-in (rax, rcx, r8, r9) */
  u64 gpr_in[4] = {0};
  u64 frame = 0;
  for (int i = 0; i < ld_case.nargs; i++) {
    u64 v = ld_case.val[i];
    if (i == 0) frame = v;
    else if (i < 5) gpr_in[i - 1] = v;
  }
  u64 out[4] = {0};
  void* fn = (void*)(uintptr_t)ld_case.fn;
  if (ld_case.fn < g_imgbase || ld_case.fn >= g_imgbase + g_imgsize) {
    puts(ld_case_end("bad_fn", "fn outside image", 0, 0, 0, 0, 0, 0, 0)); fflush(stdout); return;
  }
  g_sig = 0; g_pending = NULL;
  if (ld_case.trace) tr_arm();
  struct itimerval it = { {0, 0}, {1, 500000} };
  if (sigsetjmp(g_jb, 1) == 0) {
    g_in_call = 1; setitimer(ITIMER_REAL, &it, NULL);
    lp_call(fn, frame, gpr_in, out);
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    puts(ld_case_end("ok", NULL, 0, 0, out[0], out[1], out[2], out[3], 1));
  } else {
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    u64 rip = g_fault_rip;
    char det[128]; snprintf(det, sizeof det, "rip_rva=%#llx", (unsigned long long)(rip - g_imgbase));
    puts(ld_case_end(signame(g_sig), det, g_fault_addr, rip, 0, 0, 0, 0, 0));
  }
  fflush(stdout);
}

static char* g_line; static size_t g_linecap;
int main(int argc, char** argv) {
  if (argc < 2) { fprintf(stderr, "usage: lp_native <pe>\n"); return 2; }
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
    } else if (!strncmp(l, "PATCHSET ", 9)) {
      /* PATCHSET <rva:hex;rva:hex;...> — ld_img へ恒久 patch (INT3 より先に適用する事で
       * TRACESET の orig 保存が patch 済みバイトになり、単歩復帰後も patch が生きる) */
      char* sv2;
      for (char* t = strtok_r(l + 9, ";", &sv2); t; t = strtok_r(NULL, ";", &sv2)) {
        char* c = strchr(t, ':'); if (!c) continue; *c = 0;
        u64 rva = strtoull(t, NULL, 0);
        u8 buf[64]; int n = ld_unhex(c + 1, buf, 64);
        if (n > 0 && rva + n <= g_imgsize) memcpy(ld_img + rva, buf, n);
      }
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
    } else if (!strncmp(l, "PEEK ", 5)) {
      char tok[64]; int cnt = 0; if (sscanf(l + 5, "%63s %d", tok, &cnt) == 2) {
        u8* p = (u8*)(uintptr_t)ld_parse_val(tok); ld_ob_reset(); ld_hex(p, cnt); puts(ld_out); fflush(stdout); }
    } else if (!strcmp(l, "STATE")) {
      puts(ld_state_dump()); fflush(stdout);
    } else if (!strcmp(l, "QUIT")) break;
  }
  return 0;
}
