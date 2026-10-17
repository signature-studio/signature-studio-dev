/* liftdiff native ランナ: PE x64 を preferred ImageBase に敷設し、関数 VA を MS x64 ABI で直接実行する。
 * stdin: 1 行プロトコル (LAYOUT/WR/SNAPSHOT/BLOB/FIX/TRACESET/CASE/QUIT)、stdout: 1 case 1 行 JSON。
 * 使い方: ld_native <pe-file>
 */
#define _GNU_SOURCE
#include "ld_core.h"
#include <signal.h>
#include <sched.h>
#include <setjmp.h>
#include <ucontext.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <stddef.h>
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>

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
u64 ld_stub_ent;   /* ld_ms_call.S が stub 入口の rsp を入れる ([rsp] = 呼出元の戻り番地) */

/* WIN-34 (#3557): env LD_WINTRACE_OUT=<path> で、窓まわりの import (RegisterClassW・GetClassInfoW・CreateWindowExW) の
 * 呼出元 VA・引数・戻り値を 1 呼出し 1 行で <path> へ追記する (既定は無効。応答は変えない)。 */
static const char* g_wt_path; static FILE* g_wt_fp; static int g_wt_init;
static int wt_on(const char* n) {
  if (!g_wt_init) { g_wt_init = 1; g_wt_path = getenv("LD_WINTRACE_OUT"); if (g_wt_path && *g_wt_path) g_wt_fp = fopen(g_wt_path, "a"); }
  if (!g_wt_fp) return 0;
  return !strcmp(n, "CreateWindowExW") || !strcmp(n, "RegisterClassW") || !strcmp(n, "GetClassInfoW");
}
static void wt_str(u64 p, char* out, int max) {
  if (!p) { snprintf(out, max, "null"); return; }
  if (p < 0x10000) { snprintf(out, max, "atom:0x%llx", (unsigned long long)p); return; }
  if (!ld_dst_ok(p, 2)) { snprintf(out, max, "bad:0x%llx", (unsigned long long)p); return; }
  ld_read_strW(p, out, max);
}
static void wt_rec(const char* n, u64 a0, u64 a1, u64 a2, u64 a3, const u64* stk, u64 r) {
  u64 ent = ld_stub_ent, ret = 0, s[8] = {0};
  if (ld_dst_ok(ent, 8)) memcpy(&ret, (void*)(uintptr_t)ent, 8);
  char c1[160], c2[160];
  fprintf(g_wt_fp, "wt case=%s fn=%s ret_va=0x%llx ret_rva=0x%llx stk_minus_entry=%lld ", ld_case.id, n,
          (unsigned long long)ret, (unsigned long long)(ret - g_imgbase), (long long)((u64)(uintptr_t)stk - ent));
  if (!strcmp(n, "CreateWindowExW")) {   /* ms64: 第5〜12引数は entry+0x28 から (shadow 0x20 + 戻り番地 8) */
    if (ld_dst_ok(ent + 0x28, 64)) memcpy(s, (void*)(uintptr_t)(ent + 0x28), 64);
    wt_str(a1, c1, sizeof c1); wt_str(a2, c2, sizeof c2);
    fprintf(g_wt_fp, "ex=0x%llx class=\"%s\" wname=\"%s\" style=0x%llx x=0x%llx y=0x%llx w=0x%llx h=0x%llx parent=0x%llx menu=0x%llx inst=0x%llx param=0x%llx r=0x%llx\n",
            (unsigned long long)a0, c1, c2, (unsigned long long)a3, (unsigned long long)s[0], (unsigned long long)s[1],
            (unsigned long long)s[2], (unsigned long long)s[3], (unsigned long long)s[4], (unsigned long long)s[5],
            (unsigned long long)s[6], (unsigned long long)s[7], (unsigned long long)r);
  } else if (!strcmp(n, "RegisterClassW")) {   /* WNDCLASSW: style@0 lpfnWndProc@8 hInstance@24 lpszClassName@64 */
    u32 style = 0; u64 wp = 0, hi = 0, cn = 0;
    if (ld_dst_ok(a0, 72)) { memcpy(&style, (void*)(uintptr_t)a0, 4); memcpy(&wp, (void*)(uintptr_t)(a0 + 8), 8);
      memcpy(&hi, (void*)(uintptr_t)(a0 + 24), 8); memcpy(&cn, (void*)(uintptr_t)(a0 + 64), 8); }
    wt_str(cn, c1, sizeof c1);
    fprintf(g_wt_fp, "style=0x%x wndproc_rva=0x%llx hinst=0x%llx class=\"%s\" r=0x%llx\n", style,
            (unsigned long long)(wp - g_imgbase), (unsigned long long)hi, c1, (unsigned long long)r);
  } else {
    wt_str(a1, c1, sizeof c1);
    fprintf(g_wt_fp, "class=\"%s\" r=0x%llx\n", c1, (unsigned long long)r);
  }
  fflush(g_wt_fp);
}

/* LD-161 (#3563): abort helper (case の abortret=<VA>, 例 0x409730) の入口を trace hit で保存する。
 * helper は必ず abort 経路 (RaiseException は noncontinuable) に入り、その RaiseException で入口の return 状態へ戻す
 * (rsp+8・rip=戻り先・rax=0・callee-saved と xmm は入口の値)。native 専用 (wasm は trace の int3 を持たない)。 */
static greg_t g_ab_gr[NGREG]; static struct _libc_fpstate g_ab_fp; static sigset_t g_ab_mask; static u64 g_ab_va; static int g_ab_valid;
static void ab_save(ucontext_t* uc, u64 addr) {
  memcpy(g_ab_gr, uc->uc_mcontext.gregs, sizeof g_ab_gr);
  g_ab_gr[REG_RIP] = (greg_t)addr; g_ab_gr[REG_EFL] &= ~0x100;
  g_ab_fp = *uc->uc_mcontext.fpregs; g_ab_mask = uc->uc_sigmask; g_ab_valid = 1;
}
static void __attribute__((noreturn)) ab_return(void) {
  ucontext_t uc; memset(&uc, 0, sizeof uc);
  uc.uc_sigmask = g_ab_mask;
  memcpy(uc.uc_mcontext.gregs, g_ab_gr, sizeof g_ab_gr);
  greg_t sp = g_ab_gr[REG_RSP];
  uc.uc_mcontext.gregs[REG_RIP] = *(greg_t*)(uintptr_t)sp;
  uc.uc_mcontext.gregs[REG_RSP] = sp + 8;
  uc.uc_mcontext.gregs[REG_RAX] = 0;
  uc.uc_mcontext.fpregs = &g_ab_fp;
  g_ab_valid = 0;
  setcontext(&uc);
  abort();
}

#ifdef LD_GUI_HL   /* WIN-35 (#3618): tools/gui の shim への接続 (-DLD_GUI_HL のビルドだけ・実行時は LD_GUI_HL=1) */
extern int64_t RegisterClassW(int64_t);
extern int64_t CreateWindowExW(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t);
extern int64_t DefWindowProcW(int64_t, int64_t, int64_t, int64_t);
extern int64_t SetWindowLongPtrW(int64_t, int64_t, int64_t);
extern int64_t GetClassInfoW(int64_t, int64_t, int64_t);
extern int64_t WindowFromPoint(int64_t);
void ld_gui_init(void);
void ld_gui_dump(FILE* f, const char* cid);
static int g_gui_on; static FILE* g_gui_fp;
#endif

u64 ld_stub_c(u64 idx, u64 a0, u64 a1, u64 a2, u64 a3, const u64* stk) {
  const char* n = "?bad";
  if (idx >= LD_FAKEPROC_MARK) n = ld_fakeproc_name(idx - LD_FAKEPROC_MARK);   /* GetProcAddress 仮 proc */
  else if (idx < (u64)g_nimp) n = g_impname[idx];
  u64 a4 = 0, a5 = 0;                                 /* 既定 0 */
  if (stk && (strcmp(n, "MultiByteToWideChar") == 0 || strcmp(n, "WideCharToMultiByte") == 0)) {
    a4 = stk[0]; a5 = stk[1];                          /* MS 第5/6引数 (6引数 API のみ読む) */
  }
  u64 r = ld_stub(n, a0, a1, a2, a3, a4, a5);
#ifdef LD_GUI_HL
  if (g_gui_on && (!strcmp(n, "GetClassInfoW") || !strcmp(n, "RegisterClassW") || !strcmp(n, "CreateWindowExW") || !strcmp(n, "DefWindowProcW") || !strcmp(n, "SetWindowLongPtrW") || !strcmp(n, "WindowFromPoint"))) {
    u64 ent0 = ld_stub_ent, s[8] = {0};   /* 第5〜12引数は entry+0x28 (wt_rec と同じ) */
    int ci = (int)ld_ncalls - 1;          /* 直前の ld_stub が積んだ記録 (呼出し記録の戻り値も直す) */
    if (!strcmp(n, "CreateWindowExW") && ld_dst_ok(ent0 + 0x28, 64)) memcpy(s, (void*)(uintptr_t)(ent0 + 0x28), 64);
    if (!strcmp(n, "GetClassInfoW")) r = (u64)GetClassInfoW((int64_t)a0, (int64_t)a1, (int64_t)a2);
    else if (!strcmp(n, "RegisterClassW")) r = (u64)RegisterClassW((int64_t)a0);
    else if (!strcmp(n, "DefWindowProcW")) r = (u64)DefWindowProcW((int64_t)a0, (int64_t)a1, (int64_t)a2, (int64_t)a3);
    else if (!strcmp(n, "SetWindowLongPtrW")) r = (u64)SetWindowLongPtrW((int64_t)a0, (int64_t)a1, (int64_t)a2);
    else if (!strcmp(n, "WindowFromPoint")) r = (u64)WindowFromPoint((int64_t)a0);   /* POINT は 8B 値渡し (x 下位 / y 上位) */
    else r = (u64)CreateWindowExW((int64_t)a0, (int64_t)a1, (int64_t)a2, (int64_t)a3, (int64_t)s[0], (int64_t)s[1], (int64_t)s[2], (int64_t)s[3],
                                  (int64_t)s[4], (int64_t)s[5], (int64_t)s[6], (int64_t)s[7]);
    ld_stub_ent = ent0;   /* 窓プロシージャの nested 呼出しで上書きされた入口を戻す */
    if (ci >= 0 && ci < LD_MAX_CALLS && ld_calls[ci].name == n) ld_calls[ci].ret = r;
  }
#endif
  if (wt_on(n)) wt_rec(n, a0, a1, a2, a3, stk, r);
  if (g_ab_valid && (a1 & 1) && strcmp(n, "RaiseException") == 0) ab_return();   /* LD-161: abort (noncontinuable) は入口の return へ */
  return r;
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
static u64 g_mem_va, g_mem_last, g_mem_rva; static int g_mem_on;   /* WIN-33 (#3556): LD_STEP_MEM=<VA hex> で 8B の変化を記録 */
static void step_rec(greg_t* g) {
  if (!g_in_call || g_step_cnt >= g_step_max) { g[REG_EFL] &= ~0x100; g_step_on = 0; return; }
  u64 rip = (u64)g[REG_RIP];
  if (g_mem_on) {
    u64 cur = *(u64*)(uintptr_t)g_mem_va;
    if (cur != g_mem_last) {
      fprintf(g_step_fp, "MEM writer_last_img_rva=%llx old=%llx new=%llx step=%llu rip_now=%llx\n", (unsigned long long)g_mem_rva,
              (unsigned long long)g_mem_last, (unsigned long long)cur, (unsigned long long)g_step_cnt, (unsigned long long)(rip - g_imgbase));
      g_mem_last = cur;
    }
  }
  if (rip >= g_imgbase && rip < g_imgbase + g_imgsize) {
    g_mem_rva = rip - g_imgbase;
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
  { const char* sid = getenv("LD_STEP_ID"); if (sid && strcmp(sid, ld_case.id)) return; }   /* WIN-33 (#3556): 指定 case id だけ trace */
  char path[512]; snprintf(path, sizeof path, "%s.%s", o, ld_case.id);
  g_step_fp = fopen(path, "w"); if (!g_step_fp) return;
  g_step_max = (u64)atoll(n); g_step_entry = ld_case.fn; g_step_orig = *(u8*)(uintptr_t)ld_case.fn; g_step_armed = 1;
  { const char* mv = getenv("LD_STEP_MEM"); g_mem_on = 0; if (mv && *mv) { g_mem_va = strtoull(mv, NULL, 16); g_mem_last = *(u64*)(uintptr_t)g_mem_va; g_mem_on = 1; g_mem_rva = 0; } }
  *(u8*)(uintptr_t)ld_case.fn = 0xCC;
}
static void step_end(void) {
  if (g_step_armed) { *(u8*)(uintptr_t)g_step_entry = g_step_orig; g_step_armed = 0; }
  g_step_on = 0; g_step_max = 0;
  if (g_step_fp) { fclose(g_step_fp); g_step_fp = NULL; }
}

/* LD-129 (#2770): VA への書込み監視。env LD_WATCH_ADDR=<VA hex>・LD_WATCH_OUT=<path> で有効 (既定は無効)。
 * 監視 page を PROT_READ|PROT_EXEC にし、書込みの SIGSEGV で書込み命令の RIP・書込み先を採る。
 * TF で書込み 1 命令だけ実行させてから page を戻す (書込みはそのまま行う。CPU 固定下の boot 状態は不変: REPORT_APPENDIX_2770.md §8.9。page 保護を変える。page 保護を変えない方式は LD_WATCH_MODE=hw (#3648))。
 * 記録は書込み先の開始アドレスが va-15..va+7 にあるもの (書込み幅 16 以下を想定)。重ならない書込みも含む superset で、取りこぼしは無い。
 * TF の待ち (g_wp_pend) の間は SIGALRM を block する (timeout で page が RWX のまま残るのを防ぐ)。
 * LD_STEP_N・trace と同時には使わない。 */
static u64 g_wp_va, g_wp_page, g_wp_rip, g_wp_addr, g_wp_old, g_wp_rsp, g_wp_rax, g_wp_rcx, g_wp_nflt, g_tmo_n;
static u8 g_wp_ins[16]; static int g_wp_call, g_wp_hit, g_wp_alrm_was; static volatile int g_wp_pend; static FILE* g_wp_fp; static u64 g_wp_alrm_def;
static void wp_prot(int rw) { mprotect((void*)(uintptr_t)g_wp_page, 4096, rw ? PROT_READ | PROT_WRITE | PROT_EXEC : PROT_READ | PROT_EXEC); }
static void wp_arm(void) {
  const char* a = getenv("LD_WATCH_ADDR"); const char* o = getenv("LD_WATCH_OUT");
  if (!a || !o || !*a || !*o) return;
  u64 va = strtoull(a, NULL, 16);
  if (va < g_imgbase || va + 8 > g_imgbase + g_imgsize) { fprintf(stderr, "[ld_native] LD_WATCH_ADDR %#llx outside image\n", (unsigned long long)va); return; }
  g_wp_fp = fopen(o, "a"); if (!g_wp_fp) return;
  g_wp_va = va; g_wp_page = va & ~0xfffull; wp_prot(0);
}
static void wp_fault(ucontext_t* uc, u64 addr) {
  greg_t* g = uc->uc_mcontext.gregs; sigset_t blk; sigemptyset(&blk); sigaddset(&blk, SIGALRM);
  g_wp_alrm_was = sigismember(&uc->uc_sigmask, SIGALRM);
  sigprocmask(SIG_BLOCK, &blk, NULL); sigaddset(&uc->uc_sigmask, SIGALRM);
  g_wp_nflt++;
  g_wp_addr = addr; g_wp_rip = (u64)g[REG_RIP]; g_wp_rsp = (u64)g[REG_RSP]; g_wp_rax = (u64)g[REG_RAX]; g_wp_rcx = (u64)g[REG_RCX];
  g_wp_call = g_in_call; g_wp_hit = addr + 16 > g_wp_va && addr < g_wp_va + 8;
  memcpy(&g_wp_old, (void*)(uintptr_t)g_wp_va, 8); memcpy(g_wp_ins, (void*)(uintptr_t)g_wp_rip, 16);
  wp_prot(1); g[REG_EFL] |= 0x100; g_wp_pend = 1;
}
static void wp_finish(ucontext_t* uc) {
  greg_t* g = uc->uc_mcontext.gregs;
  u64 nw; memcpy(&nw, (void*)(uintptr_t)g_wp_va, 8);
  wp_prot(0); g[REG_EFL] &= ~0x100; g_wp_pend = 0;
  sigset_t pn; sigpending(&pn); if (sigismember(&pn, SIGALRM)) g_wp_alrm_def++;
  if (!g_wp_alrm_was) sigdelset(&uc->uc_sigmask, SIGALRM);
  if (g_wp_hit) {
    fprintf(g_wp_fp, "wp case=%s call=%d rip_rva=%#llx rip=%#llx addr=%#llx old=%016llx new=%016llx chg=%d rsp=%#llx rax=%#llx rcx=%#llx ins=",
            ld_case.id, g_wp_call, (unsigned long long)(g_wp_rip - g_imgbase), (unsigned long long)g_wp_rip, (unsigned long long)g_wp_addr,
            (unsigned long long)g_wp_old, (unsigned long long)nw, g_wp_old != nw, (unsigned long long)g_wp_rsp,
            (unsigned long long)g_wp_rax, (unsigned long long)g_wp_rcx);
    for (int i = 0; i < 15; i++) fprintf(g_wp_fp, "%02x", g_wp_ins[i]);
    fprintf(g_wp_fp, "\n"); fflush(g_wp_fp);
  }
}

/* LD-171 (#3648): page 保護を変えない書込み監視。env LD_WATCH_MODE=hw・LD_WATCH_ADDR=<VA hex>・LD_WATCH_OUT=<path> で有効。
 * 子 (guest 本体) は PTRACE_TRACEME で親の監視下に入り、load_pe の後に raise(SIGSTOP) で止まる。親はそこで DR0 に va・
 * DR1 に va-8 を置き (各 8 byte・書込みのみ)、DR7 で有効化する。以後の signal は子へ戻す (DR hit の SIGTRAP は戻さない)。
 * 書込み命令の完了後にトラップするので、記録の RIP は書込み命令の直後。trap 1 回につき 1 行 (dr6 の bit で当たった枠を示す)。
 * va-8 を足すのは page 方式の窓 [va-15, va+7] に合わせるため (C の 248 件の内訳は va が 247・va-8 が 1)。 */
#define HW_NSLOT 2
static u64 g_hw_va;
#define HW_DR_OFF(i) ((void*)(uintptr_t)(offsetof(struct user, u_debugreg) + (i) * 8))
static void __attribute__((noreturn)) hw_watch_parent(pid_t pid, u64 va) {
  const char* o = getenv("LD_WATCH_OUT");
  FILE* fp = (o && *o) ? fopen(o, "a") : NULL;
  u64 sl[HW_NSLOT] = { va, va - 8 }, old[HW_NSLOT] = { 0, 0 };
  int armed = 0; u64 hits = 0, stops = 0;
  for (;;) {
    int st;
    if (waitpid(pid, &st, 0) < 0) { if (errno == EINTR) continue; perror("[ld_native] hw watch waitpid"); _exit(7); }
    if (WIFEXITED(st) || WIFSIGNALED(st)) {
      int rc = WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
      if (fp) { fprintf(fp, "hwsum hits=%llu stops=%llu rc=%d\n", (unsigned long long)hits, (unsigned long long)stops, rc); fclose(fp); }
      _exit(rc);
    }
    int sig = WSTOPSIG(st); stops++;
    if (!armed && sig == SIGSTOP) {
      int bad = ptrace(PTRACE_SETOPTIONS, pid, NULL, (void*)(uintptr_t)PTRACE_O_EXITKILL) != 0;
      u64 dr7 = 0;
      for (int i = 0; i < HW_NSLOT; i++) {
        bad |= ptrace(PTRACE_POKEUSER, pid, HW_DR_OFF(i), (void*)(uintptr_t)sl[i]) != 0;
        dr7 |= (1ull << (2 * i)) | (1ull << (16 + 4 * i)) | (2ull << (18 + 4 * i));   /* Li=1・RWi=01 (書込み)・LENi=10 (8 byte) */
        old[i] = (u64)ptrace(PTRACE_PEEKDATA, pid, (void*)(uintptr_t)sl[i], NULL);
      }
      bad |= ptrace(PTRACE_POKEUSER, pid, HW_DR_OFF(7), (void*)(uintptr_t)dr7) != 0;
      if (bad) { perror("[ld_native] hw watch POKEUSER"); kill(pid, SIGKILL); _exit(9); }
      if (fp) fprintf(fp, "hwarm va=%#llx slot1=%#llx dr7=%#llx old0=%016llx old1=%016llx\n", (unsigned long long)va,
                      (unsigned long long)sl[1], (unsigned long long)dr7, (unsigned long long)old[0], (unsigned long long)old[1]);
      armed = 1; ptrace(PTRACE_CONT, pid, NULL, NULL); continue;
    }
    if (armed && sig == SIGTRAP) {
      u64 dr6 = (u64)ptrace(PTRACE_PEEKUSER, pid, HW_DR_OFF(6), NULL);
      if (dr6 & 0xf) {
        struct user_regs_struct r; ptrace(PTRACE_GETREGS, pid, NULL, &r);
        u64 nw[HW_NSLOT];
        for (int i = 0; i < HW_NSLOT; i++) nw[i] = (u64)ptrace(PTRACE_PEEKDATA, pid, (void*)(uintptr_t)sl[i], NULL);
        hits++;
        if (fp) fprintf(fp, "hw rip=%#llx dr6=%llx a0=%#llx old0=%016llx new0=%016llx chg0=%d a1=%#llx old1=%016llx new1=%016llx chg1=%d rsp=%#llx rax=%#llx rcx=%#llx\n",
                        (unsigned long long)r.rip, (unsigned long long)(dr6 & 0xf),
                        (unsigned long long)sl[0], (unsigned long long)old[0], (unsigned long long)nw[0], old[0] != nw[0],
                        (unsigned long long)sl[1], (unsigned long long)old[1], (unsigned long long)nw[1], old[1] != nw[1],
                        (unsigned long long)r.rsp, (unsigned long long)r.rax, (unsigned long long)r.rcx);
        for (int i = 0; i < HW_NSLOT; i++) old[i] = nw[i];
        ptrace(PTRACE_POKEUSER, pid, HW_DR_OFF(6), NULL);
        ptrace(PTRACE_CONT, pid, NULL, (void*)((dr6 & 0x4000) ? (uintptr_t)SIGTRAP : 0));   /* BS (single-step) 同時なら信号を戻す */
        continue;
      }
    }
    ptrace(PTRACE_CONT, pid, NULL, (void*)(uintptr_t)sig);
  }
}

/* LD-220 (#4466): 戻り値の直接計測。env LD_RETPROBE_VA=<entry VA hex>・LD_RETPROBE_OUT=<path> で有効 (既定は無効)。
 * entry の int3 で [rsp] (戻り番地) を読み、戻り番地にも int3 を置いて、戻った時点の rax を記録する。
 * 記録は 1 呼出し 1 行: rp case=<id> rsp_delta=<戻り時 rsp - entry rsp (正常なら 8)> ret_rva=<戻り番地> rax=<戻り値> rcx・rdx=<entry 時>。 */
static u64 g_rp_va, g_rp_ret, g_rp_rsp, g_rp_rcx, g_rp_rdx; static u8 g_rp_eorig, g_rp_rorig; static int g_rp_on; static FILE* g_rp_fp; static int g_rp_run;
static void rp_init(void) {
  const char* a = getenv("LD_RETPROBE_VA"); const char* o = getenv("LD_RETPROBE_OUT");
  if (!a || !o || !*a || !*o) return;
  u64 va = strtoull(a, NULL, 16);
  if (va < g_imgbase || va >= g_imgbase + g_imgsize) { fprintf(stderr, "[ld_native] LD_RETPROBE_VA %#llx outside image\n", (unsigned long long)va); return; }
  g_rp_fp = fopen(o, "a"); if (!g_rp_fp) return;
  g_rp_va = va; g_rp_on = 1;
}
static void rp_arm(void) {
  if (!g_rp_on) return;
  g_rp_ret = 0; g_rp_eorig = *(u8*)(uintptr_t)g_rp_va; *(u8*)(uintptr_t)g_rp_va = 0xCC;
}
static void rp_disarm(void) {
  if (!g_rp_on) return;
  *(u8*)(uintptr_t)g_rp_va = g_rp_eorig;
  if (g_rp_ret) { *(u8*)(uintptr_t)g_rp_ret = g_rp_rorig; g_rp_ret = 0; }
}

static void on_sig(int sig, siginfo_t* si, void* ucv) {
  ucontext_t* uc = (ucontext_t*)ucv; greg_t* g = uc->uc_mcontext.gregs;
  if (g_wp_va && sig == SIGTRAP && g_wp_pend) { wp_finish(uc); return; }
  if (g_wp_va && (sig == SIGSEGV || sig == SIGBUS)) {
    u64 fa = (u64)(uintptr_t)si->si_addr;
    if (fa >= g_wp_page && fa < g_wp_page + 4096) { wp_fault(uc, fa); return; }
  }
  if (sig == SIGTRAP && g_step_on) { step_rec(g); return; }
  if (sig == SIGTRAP && g_in_call && g_step_armed && (u64)g[REG_RIP] - 1 == g_step_entry) {
    *(u8*)(uintptr_t)g_step_entry = g_step_orig; g_step_armed = 0; g[REG_RIP] = (greg_t)g_step_entry; g_step_on = 1;
    step_rec(g); return;
  }
  if (sig == SIGTRAP && g_in_call) {
    if (g_pending) { *g_pending = 0xCC; g_pending = NULL; g[REG_EFL] &= ~0x100; return; }
    if (g_rp_on) {
      u64 ra = (u64)g[REG_RIP] - 1;
      if (ra == g_rp_va) {
        g_rp_rsp = (u64)g[REG_RSP]; g_rp_rcx = (u64)g[REG_RCX]; g_rp_rdx = (u64)g[REG_RDX];
        u64 ret = *(u64*)(uintptr_t)g_rp_rsp;
        if (ret >= g_imgbase && ret < g_imgbase + g_imgsize && tr_find(ret) < 0) { g_rp_ret = ret; g_rp_rorig = *(u8*)(uintptr_t)ret; *(u8*)(uintptr_t)ret = 0xCC; }
        if (tr_find(ra) < 0) {   /* trace 集合に無い entry は、ここで元の命令を 1 命令実行して再武装する (trace 集合と重なるときは下の trace 処理に任せる) */
          *(u8*)(uintptr_t)ra = g_rp_eorig; g[REG_RIP] = (greg_t)ra; g[REG_EFL] |= 0x100; g_pending = (u8*)(uintptr_t)ra;
          return;
        }
      }
      if (g_rp_ret && ra == g_rp_ret) {
        fprintf(g_rp_fp, "rp run=%d case=%s rsp_delta=%lld ret_rva=%#llx rax=%#llx rcx=%#llx rdx=%#llx\n", g_rp_run, ld_case.id,
                (long long)((u64)g[REG_RSP] - g_rp_rsp), (unsigned long long)(ra - g_imgbase), (unsigned long long)g[REG_RAX],
                (unsigned long long)g_rp_rcx, (unsigned long long)g_rp_rdx);
        fflush(g_rp_fp);
        *(u8*)(uintptr_t)ra = g_rp_rorig; g_rp_ret = 0; g[REG_RIP] = (greg_t)ra;
        return;
      }
    }
    u64 addr = (u64)g[REG_RIP] - 1; int k = tr_find(addr);
    if (k >= 0) {
      if (addr == g_ab_va) ab_save(uc, addr);
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
    if (sig == SIGALRM) g_tmo_n++;
    g[REG_EFL] &= ~0x100;
    if (g_wp_pend) { wp_prot(0); g_wp_pend = 0; }
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
  g_sig = 0; g_pending = NULL; g_fault_rsp = 0; g_fault_stk[0] = 0; g_rp_run++;
  g_ab_va = ld_case.trace ? ld_case.abortret : 0; g_ab_valid = 0;
  for (int j = 0; j < 8; j++) g_fault_g[j] = 0;
  scrub_stack(ld_case.stkfill);
  step_begin();
  rp_arm();
  if (ld_case.trace && !g_step_max) tr_arm();
  long tmo_us = 1500000; { const char* tm = getenv("LD_CASE_TMO_US"); if (tm && atol(tm) > 0) tmo_us = atol(tm); }   /* WIN-33 (#3556): 既定 1.5 s */
  struct itimerval it = { {0, 0}, {tmo_us / 1000000, tmo_us % 1000000} };
  struct timespec t0, t1;
  ld_native_ms = -1.0;
  unsigned int host_mx = 0; __asm__ volatile("stmxcsr %0" : "=m"(host_mx));   /* ゲストの MXCSR (全例外 unmask) を host に持ち込まない (LD-161, #3563) */
  if (sigsetjmp(g_jb, 1) == 0) {
    g_in_call = 1; setitimer(ITIMER_REAL, &it, NULL);
    clock_gettime(CLOCK_MONOTONIC, &t0);
    ld_ms_call(fn, gpr, xmm, stk, nstk, out, ld_case.rax);
    __asm__ volatile("ldmxcsr %0" : : "m"(host_mx));
    clock_gettime(CLOCK_MONOTONIC, &t1);
    ld_native_ms = (double)(t1.tv_sec - t0.tv_sec) * 1e3 + (double)(t1.tv_nsec - t0.tv_nsec) / 1e6;
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    rp_disarm();
    step_end();
    puts(ld_case_end("ok", NULL, 0, 0, out[0], out[1], out[2], out[3], 1));
  } else {
    __asm__ volatile("ldmxcsr %0" : : "m"(host_mx));
    struct itimerval z = {{0,0},{0,0}}; setitimer(ITIMER_REAL, &z, NULL);
    g_in_call = 0;
    if (ld_case.trace) tr_disarm();
    rp_disarm();
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
#ifdef LD_GUI_HL
  if (g_gui_on) ld_gui_dump(g_gui_fp, ld_case.id);
#endif
  fflush(stdout);
}

/* LD-209 (#4305): native 側の候補別 SNAPSHOT/RESET (ld_wasm.c の ld_w_snapshot と ld_runner.mjs の resetRegions と同じ mask: 1=stk・2=sta・4=img)。
 * stk: SNAPSHOT 時の sp より下 [sp-128K, sp-8K) (run_case の scrub 域。RESET の呼出し枠より下の 8K 帯は含めない)。
 * sta: 実行器の data/bss [__data_start, _end) から、ld_heap 管理変数・ld_blks・入力行 buffer・TRACESET・nrst 自身の管理表 (g_nrst/g_nnrst) の状態を除いた残り。
 * img: PE image [ld_img, ld_img+SizeOfImage)。 */
extern char __data_start[], _end[];
#define NRST_STK_TOP (8u << 10)
#define NRST_STK_LEN (128u << 10)
#define NRST_MAX 64
#define NRST_MMAP 8   /* LD-229 (#4631): anon の rw-p mmap (ヒープ外・stdio buffer 等)。guest の arena・heap・image と stack/brk/file 領域は含めない */
typedef struct { u8* lo; u64 n; u8* pr; int cat; } nrst_t;
static nrst_t g_nrst[NRST_MAX]; static int g_nnrst;
static void nrst_add_mmap(void);
static char* g_line; static size_t g_linecap;   /* getline の buffer (実行中に realloc される。戻すと解放済みを指す) */
static void nrst_add(int cat, void* lo, u64 n) {
  if (!n || g_nnrst >= NRST_MAX) return;
  nrst_t* r = &g_nrst[g_nnrst++]; r->lo = (u8*)lo; r->n = n; r->cat = cat; r->pr = (u8*)malloc(n); memcpy(r->pr, r->lo, n);
}
static void __attribute__((noinline)) nrst_snap(void) {
  volatile u8 probe = 0;
  for (int i = 0; i < g_nnrst; i++) free(g_nrst[i].pr);
  g_nnrst = 0;
  u8* sp = (u8*)&probe;
  nrst_add(1, sp - NRST_STK_LEN, NRST_STK_LEN - NRST_STK_TOP);
  u8* ex[32]; u64 exn[32]; int nx = 0;
#define NRST_EX(p, n) do { ex[nx] = (u8*)(p); exn[nx] = (n); nx++; } while (0)
  NRST_EX(&ld_heap_used, sizeof ld_heap_used); NRST_EX(&ld_heap_hw, sizeof ld_heap_hw);
  NRST_EX(&ld_heap_pristine, sizeof ld_heap_pristine); NRST_EX(&ld_heap_pristine_len, sizeof ld_heap_pristine_len);
  NRST_EX(&ld_heap_pristine_used, sizeof ld_heap_pristine_used); NRST_EX(&ld_blks, sizeof ld_blks);
  NRST_EX(&ld_nblk, sizeof ld_nblk);
  NRST_EX(&ld_arena_pristine, sizeof ld_arena_pristine); NRST_EX(&ld_wr, sizeof ld_wr); NRST_EX(&ld_nwr, sizeof ld_nwr);
  NRST_EX(&g_line, sizeof g_line); NRST_EX(&g_linecap, sizeof g_linecap);
  NRST_EX(&g_tr_va, sizeof g_tr_va); NRST_EX(&g_tr_orig, sizeof g_tr_orig);
  NRST_EX(&g_ntr_set, sizeof g_ntr_set);
  NRST_EX(&g_nrst, sizeof g_nrst); NRST_EX(&g_nnrst, sizeof g_nnrst);
  /* 除外区間を番地順に並べて、その間を sta として登録する */
  for (int i = 1; i < nx; i++) for (int j = i; j > 0 && ex[j] < ex[j - 1]; j--) {
    u8* t = ex[j]; ex[j] = ex[j - 1]; ex[j - 1] = t; u64 k = exn[j]; exn[j] = exn[j - 1]; exn[j - 1] = k;
  }
  u8* cur = (u8*)__data_start;
  for (int i = 0; i < nx; i++) {
    if (ex[i] > cur) nrst_add(2, cur, (u64)(ex[i] - cur));
    if (ex[i] + exn[i] > cur) cur = ex[i] + exn[i];
  }
  if ((u8*)_end > cur) nrst_add(2, cur, (u64)((u8*)_end - cur));
  nrst_add(4, ld_img, g_imgsize);
  nrst_add_mmap();
}
/* LD-229 (#4631): anon の rw-p mapping (libc の mmap 領域・stdio buffer 等) を候補 NRST_MMAP として登録する。
 * 除外: path 付き (image・stack・[heap]・file 領域)、guest の arena・heap・image、g_file (PE の読込み copy)、
 * 本表の複製 buffer 自身 (複製が mmap されると自分を戻してしまう)。
 * 登録後に munmap された領域は reset で戻さない (msync の ENOMEM で判定)。 */
static void __attribute__((noinline)) nrst_add_mmap(void) {
  u8* ex[16]; int nx = 0;
  ex[nx++] = (u8*)ld_arena; ex[nx++] = (u8*)ld_heap; ex[nx++] = ld_img; ex[nx++] = g_file;
  for (int i = 0; i < g_nnrst && nx < 16; i++) ex[nx++] = g_nrst[i].pr;
  FILE* f = fopen("/proc/self/maps", "r"); if (!f) return;
  char line[512];
  while (fgets(line, sizeof line, f)) {
    unsigned long lo, hi; char perm[8], path[256] = "";
    if (sscanf(line, "%lx-%lx %7s %*s %*s %*s %255s", &lo, &hi, perm, path) < 3) continue;
    if (strcmp(perm, "rw-p") || path[0]) continue;
    u8* a = (u8*)(uintptr_t)lo; u64 n = (u64)(hi - lo); int skip = 0;
    for (int k = 0; k < nx; k++) if (ex[k] && ex[k] >= a && ex[k] < a + n) skip = 1;
    if (skip) continue;
    if (g_nnrst >= NRST_MAX) { fprintf(stderr, "[ld_native] nrst table full (mmap regions truncated)\n"); break; }
    nrst_add(NRST_MMAP, a, n);
  }
  fclose(f);
}
static u64 g_nrst_skip;   /* reset で戻せなかった (munmap 済みの) 区間の数 */
/* LD-268 (#5268): NRST_MMAP の k 番目 (0 始まり) だけを戻す。ntot に NRST_MMAP の総数を返す */
static u64 nrst_reset_mmap_at(int k, int* ntot) {
  u64 diff = 0; g_nrst_skip = 0; int c = 0;
  for (int i = 0; i < g_nnrst; i++) if (g_nrst[i].cat == NRST_MMAP) {
    if (c++ != k) continue;
    if (msync(g_nrst[i].lo, g_nrst[i].n, MS_ASYNC) != 0) { g_nrst_skip++; continue; }
    for (u64 q = 0; q < g_nrst[i].n; q++) diff += g_nrst[i].lo[q] != g_nrst[i].pr[q];
    memcpy(g_nrst[i].lo, g_nrst[i].pr, g_nrst[i].n);
  }
  if (ntot) *ntot = c;
  return diff;
}
static u64 nrst_reset(int mask) {
  u64 diff = 0; g_nrst_skip = 0;
  for (int i = 0; i < g_nnrst; i++) if (mask & g_nrst[i].cat) {
    if (g_nrst[i].cat == NRST_MMAP && msync(g_nrst[i].lo, g_nrst[i].n, MS_ASYNC) != 0) { g_nrst_skip++; continue; }
    for (u64 k = 0; k < g_nrst[i].n; k++) diff += g_nrst[i].lo[k] != g_nrst[i].pr[k];
    memcpy(g_nrst[i].lo, g_nrst[i].pr, g_nrst[i].n);
  }
  return diff;
}
int main(int argc, char** argv) {
  if (argc < 2) { fprintf(stderr, "usage: ld_native <pe>\n"); return 2; }
  setvbuf(stdout, NULL, _IOFBF, 1 << 20);
  const char* pin = getenv("LD_PIN_CPU");   /* #2770: boot 状態は実行 CPU 番号に依存する (§8.9)。比較時は env で CPU を固定する */
  if (pin && *pin) {
    char* end = NULL; long cpu = strtol(pin, &end, 10);
    if (*end || cpu < 0 || cpu >= CPU_SETSIZE) { fprintf(stderr, "usage: LD_PIN_CPU=<0..%d>\n", CPU_SETSIZE - 1); return 2; }
    cpu_set_t cs; CPU_ZERO(&cs); CPU_SET((int)cpu, &cs);
    if (sched_setaffinity(0, sizeof cs, &cs)) { perror("LD_PIN_CPU"); return 6; }
  }
  { const char* wm = getenv("LD_WATCH_MODE"); const char* wa = getenv("LD_WATCH_ADDR");
    if (wm && !strcmp(wm, "hw") && wa && *wa) {   /* LD-171 (#3648): 親が監視・子が guest 本体 (hw_watch_parent) */
      pid_t pid = fork();
      if (pid < 0) { perror("[ld_native] fork"); return 8; }
      if (pid) hw_watch_parent(pid, strtoull(wa, NULL, 16));
      if (ptrace(PTRACE_TRACEME, 0, NULL, NULL)) { perror("[ld_native] PTRACE_TRACEME"); return 8; }
      g_hw_va = strtoull(wa, NULL, 16);
    } }
  if (load_pe(argv[1])) return 3;
  install_signals();
  rp_init();
  if (g_hw_va) {
    if (g_hw_va < g_imgbase || g_hw_va + 8 > g_imgbase + g_imgsize) { fprintf(stderr, "[ld_native] LD_WATCH_ADDR %#llx outside image\n", (unsigned long long)g_hw_va); return 2; }
    raise(SIGSTOP);   /* 親が DR を設定する点 (load_pe の後) */
  } else wp_arm();
  { const char* cat = getenv("LD_CATALOG_MO");   /* WIN-33 (#3556): 実カタログ供給 (未設定なら従来応答) */
    if (cat && *cat) {
      FILE* cf = fopen(cat, "rb");
      if (!cf) { fprintf(stderr, "[ld_native] LD_CATALOG_MO unreadable: %s\n", cat); return 6; }
      fseek(cf, 0, SEEK_END); ld_cat_blob_len = (u64)ftell(cf); fseek(cf, 0, SEEK_SET);
      ld_cat_blob = malloc(ld_cat_blob_len ? ld_cat_blob_len : 1);
      if (!ld_cat_blob || fread(ld_cat_blob, 1, ld_cat_blob_len, cf) != ld_cat_blob_len) { fprintf(stderr, "[ld_native] LD_CATALOG_MO read failed\n"); return 6; }
      fclose(cf);
    } }
#ifdef LD_GUI_HL
  { const char* gh = getenv("LD_GUI_HL");   /* WIN-35 (#3618): 窓 import を gui shim へ向ける (既定は従来の応答) */
    if (gh && !strcmp(gh, "1")) {
      ld_gui_init(); g_gui_on = 1;
      const char* go = getenv("LD_GUI_OUT");
      g_gui_fp = (go && *go) ? fopen(go, "a") : stderr;
    } }
#endif
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
      ld_snapshot(); nrst_snap(); puts("{\"ready\":true}"); fflush(stdout);
    } else if (!strncmp(l, "NRESET ", 7)) {   /* LD-209: native の候補別 RESET (mask は wasm の RESET と同じ) */
      u64 d = nrst_reset(atoi(l + 7)); printf("{\"nreset\":%d,\"diff\":%llu,\"skip\":%llu}\n", atoi(l + 7), (unsigned long long)d, (unsigned long long)g_nrst_skip); fflush(stdout);
    } else if (!strncmp(l, "NRESETI ", 8)) {   /* LD-268 (#5268): NRST_MMAP の k 番目だけを戻す */
      int nt = 0; u64 d = nrst_reset_mmap_at(atoi(l + 8), &nt);
      printf("{\"nreseti\":%d,\"ntot\":%d,\"diff\":%llu,\"skip\":%llu}\n", atoi(l + 8), nt, (unsigned long long)d, (unsigned long long)g_nrst_skip); fflush(stdout);
    } else if (!strncmp(l, "NRESETB ", 8)) {   /* LD-268 (#5268): NRST_MMAP の k 番目の [off, off+len) だけを戻す (領域内の半分割り) */
      int k = 0; unsigned long long off = 0, len = 0; int nt = 0; u64 d = 0; g_nrst_skip = 0;
      if (sscanf(l + 8, "%d %llx %llx", &k, &off, &len) != 3) { fprintf(stderr, "bad NRESETB\n"); return 4; }
      int c = 0;
      for (int i = 0; i < g_nnrst; i++) if (g_nrst[i].cat == NRST_MMAP) {
        if (c++ != k) continue;
        if (msync(g_nrst[i].lo, g_nrst[i].n, MS_ASYNC) != 0) { g_nrst_skip++; continue; }
        u64 lo = off < g_nrst[i].n ? off : g_nrst[i].n;
        u64 hi = (off + len < g_nrst[i].n) ? off + len : g_nrst[i].n;
        for (u64 q = lo; q < hi; q++) d += g_nrst[i].lo[q] != g_nrst[i].pr[q];
        memcpy(g_nrst[i].lo + lo, g_nrst[i].pr + lo, hi - lo);
      }
      nt = c;
      printf("{\"nresetb\":%d,\"ntot\":%d,\"diff\":%llu,\"skip\":%llu}\n", k, nt, (unsigned long long)d, (unsigned long long)g_nrst_skip); fflush(stdout);
    } else if (!strncmp(l, "NRESETX ", 8)) {   /* LD-268 (#5268): NRST_MMAP の k 番目以外を全部戻す (leave-one-out) */
      int k = atoi(l + 8), nt = 0; u64 d = 0; g_nrst_skip = 0; int c = 0;
      for (int i = 0; i < g_nnrst; i++) if (g_nrst[i].cat == NRST_MMAP) {
        if (c++ == k) continue;
        if (msync(g_nrst[i].lo, g_nrst[i].n, MS_ASYNC) != 0) { g_nrst_skip++; continue; }
        for (u64 q = 0; q < g_nrst[i].n; q++) d += g_nrst[i].lo[q] != g_nrst[i].pr[q];
        memcpy(g_nrst[i].lo, g_nrst[i].pr, g_nrst[i].n);
      }
      nt = c;
      printf("{\"nresetx\":%d,\"ntot\":%d,\"diff\":%llu,\"skip\":%llu}\n", k, nt, (unsigned long long)d, (unsigned long long)g_nrst_skip); fflush(stdout);
    } else if (!strcmp(l, "NMMAPN")) {   /* LD-268: NRST_MMAP の領域数と各 (lo, n) */
      int nt = 0; nrst_reset_mmap_at(-1, &nt);
      printf("{\"nmmapn\":%d,\"regions\":[", nt);
      int c = 0; for (int i = 0; i < g_nnrst; i++) if (g_nrst[i].cat == NRST_MMAP) {
        printf("%s[\"%llx\",%llu]", c ? "," : "", (unsigned long long)(uintptr_t)g_nrst[i].lo, (unsigned long long)g_nrst[i].n); c++; }
      printf("]}\n"); fflush(stdout);
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
  if (g_wp_fp) { fprintf(g_wp_fp, "wpsum faults=%llu timeouts=%llu alrm_def=%llu\n", (unsigned long long)g_wp_nflt, (unsigned long long)g_tmo_n, (unsigned long long)g_wp_alrm_def); fclose(g_wp_fp); }
  return 0;
}
