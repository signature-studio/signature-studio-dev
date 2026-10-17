// 実インスタンス probe: win Reverb.dll の CreateReverbInstance を元の機械語のまま ms_abi で実行し、返された状態を実測する。
// build: gcc -O1 -w -o inst_probe inst_probe.c   usage: inst_probe image.bin create_rva fruity_rva [ctor|noctor|selftest]
// IAT は HeapAlloc / HeapFree の 2 件だけ C 実装に差し替える。HeapAlloc は 4096 B 境界の mmap 領域を返し、
// 書き込み観測 (mode ctor) では領域を PROT_READ にしておき、書き込みを SIGSEGV で捕まえて TF で 1 命令だけ進める。
// 捕まえた書き込みごとに RIP (書き込み命令) と書き込み後の 8 B を記録する。他の IAT は 0 のまま (到達すれば SIGSEGV で見える)。
// mode: ctor = CreateReverbInstance を呼んで観測 / noctor = 呼ばずに空の状態領域だけ観測 (陰性対照: 0 件のはず) /
//       selftest = C 側から 14 本へ書いて観測 (観測手段の対照: 14 件・RIP は image の外のはず)。
// Process_Fruity は fork した子で 1 回呼び、終了シグナルを記録する (親は落ちない)。ctor モードのみ。
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <signal.h>
#include <ucontext.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/mman.h>
typedef void *(__attribute__((ms_abi)) *CRI)(void *);
typedef void (__attribute__((ms_abi)) *FF)(void *, const float *, float *, uint32_t);
#define NL 14
#define PTR0 0xbc
#define OBJ 0x2a0
#define PG 4096UL
#define MAXREG 4096
#define MAXW 65536
#define NVT 6
static int n_alloc, n_free;
struct reg { uint8_t *base; size_t len; };
static struct reg regs[MAXREG]; static int nreg;
struct wr { uint64_t rip, addr, val; };
static struct wr ws[MAXW]; static int nw;
static volatile int tracing, pend; static int pend_idx; static uint8_t *pend_page;
static int find_reg(uint64_t a) {
  for (int i = 0; i < nreg; i++) if (a >= (uint64_t)regs[i].base && a < (uint64_t)regs[i].base + regs[i].len) return i;
  return -1;
}
static uint64_t fault_img;
static void on_segv(int sig, siginfo_t *si, void *ucv) {
  (void)sig;
  ucontext_t *uc = ucv;
  uint64_t a = (uint64_t)si->si_addr;
  int r = tracing && !pend ? find_reg(a) : -1;
  if (r < 0) {
    if (tracing) {
      char b[128];
      int n = snprintf(b, sizeof b, "FAULT addr=%#lx rip=%#lx img=%#lx\n", (unsigned long)a, (unsigned long)uc->uc_mcontext.gregs[REG_RIP], (unsigned long)fault_img);
      if (n > 0) write(1, b, n);
    }
    signal(SIGSEGV, SIG_DFL); return;
  }
  if (nw < MAXW) { ws[nw].rip = uc->uc_mcontext.gregs[REG_RIP]; ws[nw].addr = a; pend_idx = nw; nw++; }
  else pend_idx = -1;
  pend_page = (uint8_t *)(a & ~(PG - 1));
  mprotect(pend_page, PG, PROT_READ | PROT_WRITE);
  uc->uc_mcontext.gregs[REG_EFL] |= 0x100;   // TF: 書き込み命令を 1 つだけ実行して SIGTRAP
  pend = 1;
}
static volatile int emit_obj; static uint64_t emit_base, emit_img;
static void on_trap(int sig, siginfo_t *si, void *ucv) {
  (void)sig; (void)si;
  ucontext_t *uc = ucv;
  if (!pend) return;
  pend = 0;
  if (pend_idx >= 0) memcpy(&ws[pend_idx].val, (void *)ws[pend_idx].addr, 8);
  if (emit_obj && pend_idx >= 0 && ws[pend_idx].addr >= emit_base && ws[pend_idx].addr < emit_base + OBJ) {
    char b[192];
    uint64_t hi = 0; memcpy(&hi, (void *)(ws[pend_idx].addr + 8), 8);
    int n = snprintf(b, sizeof b, "EMIT off=%#lx rip_rva=%#lx val=%#lx hi=%#lx\n", (unsigned long)(ws[pend_idx].addr - emit_base),
                     (unsigned long)(ws[pend_idx].rip - emit_img), (unsigned long)ws[pend_idx].val, (unsigned long)hi);
    if (n > 0) write(1, b, n);
  }
  mprotect(pend_page, PG, PROT_READ);
  uc->uc_mcontext.gregs[REG_EFL] &= ~0x100;
}
static void *__attribute__((ms_abi)) my_HeapAlloc(void *h, uint32_t fl, size_t n) {
  (void)h; (void)fl; n_alloc++;
  size_t len = ((n ? n : 1) + PG - 1) & ~(PG - 1);
  uint8_t *p = mmap(0, len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (p == MAP_FAILED || nreg >= MAXREG) return NULL;
  regs[nreg].base = p; regs[nreg].len = len; nreg++;
  if (tracing) mprotect(p, len, PROT_READ);
  return p;
}
static int __attribute__((ms_abi)) my_HeapFree(void *h, uint32_t fl, void *p) { (void)h; (void)fl; (void)p; n_free++; return 1; }
int main(int argc, char **argv) {
  if (argc < 4 || argc > 5) { fprintf(stderr, "usage: inst_probe image.bin create_rva fruity_rva [ctor|noctor|selftest]\n"); return 2; }
  const char *mode = argc == 5 ? argv[4] : "ctor";
  FILE *fi = fopen(argv[1], "rb"); if (!fi) return 2;
  fseek(fi, 0, SEEK_END); long isz = ftell(fi); rewind(fi);
  uint8_t *img = mmap(0, (isz + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (img == MAP_FAILED || fread(img, 1, isz, fi) != (size_t)isz) return 2;
  *(void **)(img + 0x60130) = (void *)my_HeapAlloc;   // KERNEL32 HeapAlloc の IAT slot
  *(void **)(img + 0x60138) = (void *)my_HeapFree;    // KERNEL32 HeapFree の IAT slot
  struct sigaction sa; memset(&sa, 0, sizeof sa);
  sa.sa_sigaction = on_segv; sa.sa_flags = SA_SIGINFO; sigaction(SIGSEGV, &sa, NULL);
  sa.sa_sigaction = on_trap; sigaction(SIGTRAP, &sa, NULL);
  tracing = 1;
  uint8_t *obj;
  fault_img = (uint64_t)img;
  if (!strcmp(mode, "ctor") || !strcmp(mode, "vt") || !strcmp(mode, "fruity") || !strcmp(mode, "sweep") || !strcmp(mode, "sweepfull")) obj = ((CRI)(img + strtoul(argv[2], 0, 16)))(NULL);
  else {
    obj = my_HeapAlloc(NULL, 0, OBJ);
    if (!strcmp(mode, "selftest"))
      for (int i = 0; i < NL; i++) { volatile uint64_t *slot = (volatile uint64_t *)(obj + PTR0 + 8 * i); *slot = 0x1000 + i; }
  }
  tracing = 0;
  printf("MODE=%s\n", mode);
  printf("CREATE_NONNULL=%d\n", obj != NULL);
  printf("HEAPALLOC_CALLS=%d HEAPFREE_CALLS=%d\n", n_alloc, n_free);
  if (!obj) return 1;
  int oi = -1;
  for (int i = 0; i < nreg; i++) if ((uint64_t)obj == (uint64_t)regs[i].base) oi = i;
  uint64_t vt; memcpy(&vt, obj, 8);
  printf("VPTR_RVA=%#lx\n", (unsigned long)((uint8_t *)vt - img));
  int nz = 0; for (int i = 0; i < OBJ; i++) nz += obj[i] != 0;
  printf("NONZERO_BYTES=%d\n", nz);
  int zero = 0;
  for (int i = 0; i < NL; i++) { uint64_t p; memcpy(&p, obj + PTR0 + 8 * i, 8); zero += p == 0; }
  printf("PTR14_ZERO=%d\n", zero);
  int nwo = 0, nwp = 0, nwext = 0, match = 0, nslot = 0;
  uint64_t last[NL] = {0}; int seen[NL] = {0};
  for (int i = 0; i < nw; i++) {
    int r = find_reg(ws[i].addr);
    if (r < 0 || r != oi) continue;
    nwo++;
    uint64_t off = ws[i].addr - (uint64_t)obj;
    int inr = (uint64_t)img <= ws[i].rip && ws[i].rip < (uint64_t)img + (uint64_t)isz;
    if (!inr) nwext++;
    if (off >= PTR0 && off < PTR0 + 8 * NL && (off - PTR0) % 8 == 0) {
      int k = (off - PTR0) / 8; nwp++; last[k] = ws[i].val; seen[k] = 1;
      if (inr) printf("PTRW slot=%d off=%#lx rip_rva=%#lx val=%#lx\n", k, (unsigned long)off, (unsigned long)(ws[i].rip - (uint64_t)img), (unsigned long)ws[i].val);
      else printf("PTRW slot=%d off=%#lx rip=%#lx val=%#lx (image 外)\n", k, (unsigned long)off, (unsigned long)ws[i].rip, (unsigned long)ws[i].val);
    }
  }
  for (int k = 0; k < NL; k++) {
    uint64_t p; memcpy(&p, obj + PTR0 + 8 * k, 8);
    nslot += seen[k]; match += seen[k] && last[k] == p;
  }
  printf("WRITES_TOTAL=%d WRITES_OBJ=%d WRITES_PTR=%d WRITES_OUTSIDE_IMAGE=%d PTR_SLOTS_SEEN=%d\n", nw, nwo, nwp, nwext, nslot);
  printf("SLOT_LASTWRITE_EQ_FINAL=%d\n", match);
  printf("PTR14_ZERO_AFTER=%d\n", zero);
  int nother = 0, nptrval = 0;
  for (int i = 0; i < nw; i++) {
    int r = find_reg(ws[i].addr);
    if (r < 0) continue;
    int pv = -1;
    for (int j = 0; j < nreg && pv < 0; j++) if (ws[i].val >= (uint64_t)regs[j].base && ws[i].val < (uint64_t)regs[j].base + regs[j].len) pv = j;
    if (r != oi) {
      nother++;
      printf("OTHER_W region=%d off=%#lx rip_rva=%#lx val=%#lx ptr_to_region=%d\n", r, (unsigned long)(ws[i].addr - (uint64_t)regs[r].base),
             (unsigned long)(ws[i].rip - (uint64_t)img), (unsigned long)ws[i].val, pv);
    }
    nptrval += pv >= 0;
  }
  printf("OTHER_WRITES=%d PTRVAL_WRITES=%d REGIONS=%d\n", nother, nptrval, nreg);
  fflush(stdout);
  if (!strcmp(mode, "vt")) {
    uint64_t ib; memcpy(&ib, img + *(uint32_t *)(img + 0x3c) + 48, 8);
    uint64_t *vtab = (uint64_t *)(img + 0x603c0);
    for (int k = 0; k < NVT; k++) {
      uint64_t tgt = vtab[k] - ib;
      fflush(stdout);
      pid_t cp = fork();
      if (cp == 0) {
        nw = 0; pend = 0;
        mprotect(obj, OBJ, PROT_READ);
        if (oi >= 0) mprotect(regs[oi].base, regs[oi].len, PROT_READ);
        emit_obj = 1; emit_base = (uint64_t)obj; emit_img = (uint64_t)img;
        printf("VT%d_BEGIN\n", k); fflush(stdout);
        tracing = 1;
        ((void (__attribute__((ms_abi)) *)(void *))(img + tgt))(obj);
        tracing = 0;
        int nobj = 0;
        for (int i = 0; i < nw; i++) {
          if (find_reg(ws[i].addr) != oi) continue;
          nobj++;
          uint64_t off = ws[i].addr - (uint64_t)obj;
          if (off < OBJ) printf("VT%d_WRITE off=%#lx rip_rva=%#lx\n", k, (unsigned long)off, (unsigned long)(ws[i].rip - (uint64_t)img));
        }
        printf("VT%d_TARGET_RVA=%#lx WRITES_TOTAL=%d WRITES_OBJ=%d\n", k, (unsigned long)tgt, nw, nobj);
        fflush(stdout);
        _exit(0);
      }
      int st = 0; waitpid(cp, &st, 0);
      if (WIFSIGNALED(st)) printf("VT%d_SIGNAL=%d\n", k, WTERMSIG(st));
      else printf("VT%d_EXIT=%d\n", k, WEXITSTATUS(st));
      fflush(stdout);
    }
    return 0;
  }
  if (!strcmp(mode, "fruity")) {
    fflush(stdout);
    pid_t fp = fork();
    if (fp == 0) {
      float in[8] = {0.5f, -0.25f, 0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f}, out[16];
      memset(out, 0, sizeof out);
      nw = 0; pend = 0;
      if (oi >= 0) mprotect(regs[oi].base, regs[oi].len, PROT_READ);
      emit_obj = 1; emit_base = (uint64_t)obj; emit_img = (uint64_t)img;
      tracing = 1;
      ((FF)(img + strtoul(argv[3], 0, 16)))(obj, in, out, 4);
      tracing = 0;
      printf("FRUITY_WRITES_TOTAL=%d\n", nw);
      fflush(stdout);
      _exit(0);
    }
    int fst = 0; waitpid(fp, &fst, 0);
    if (WIFSIGNALED(fst)) printf("FRUITY_TRACE_SIGNAL=%d\n", WTERMSIG(fst));
    else printf("FRUITY_TRACE_EXIT=%d\n", WEXITSTATUS(fst));
    return 0;
  }
  if (!strcmp(mode, "sweep") || !strcmp(mode, "sweepfull")) {
    if (!strcmp(mode, "sweepfull")) {
      for (int i = 0; i < nreg; i++) mprotect(regs[i].base, regs[i].len, PROT_READ | PROT_WRITE);
      for (int off = 0; off + 8 <= OBJ; off += 8) {
        uint64_t v; memcpy(&v, obj + off, 8);
        if (v) continue;
        uint8_t *q = my_HeapAlloc(NULL, 0, 65536);
        memcpy(obj + off, &q, 8);
      }
    }
    uint32_t pe = *(uint32_t *)(img + 0x3c);
    uint16_t nsec = *(uint16_t *)(img + pe + 6), optsz = *(uint16_t *)(img + pe + 20);
    uint32_t pd_rva = 0, pd_sz = 0;
    for (int s = 0; s < nsec; s++) {
      uint8_t *sh = img + pe + 24 + optsz + 40 * s;
      if (!memcmp(sh, ".pdata", 6)) { pd_sz = *(uint32_t *)(sh + 8); pd_rva = *(uint32_t *)(sh + 12); }
    }
    int nfn = 0, nhit = 0;
    for (uint32_t k = 0; k + 12 <= pd_sz; k += 12) {
      uint32_t b = *(uint32_t *)(img + pd_rva + k);
      if (!b) continue;
      nfn++;
      fflush(stdout);
      pid_t sp = fork();
      if (sp == 0) {
        alarm(2);
        nw = 0; pend = 0;
        if (oi >= 0) mprotect(regs[oi].base, regs[oi].len, PROT_READ);
        emit_obj = 1; emit_base = (uint64_t)obj; emit_img = (uint64_t)img;
        float in[8] = {0.5f, -0.25f, 0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f}, out[16];
        memset(out, 0, sizeof out);
        printf("SWEEP_BEGIN=%#x\n", b); fflush(stdout);
        tracing = 1;
        ((FF)(img + b))(obj, in, out, 4);
        tracing = 0;
        printf("SWEEP_DONE=%#x\n", b); fflush(stdout);
        _exit(0);
      }
      int st = 0; waitpid(sp, &st, 0);
      if (WIFSIGNALED(st)) printf("SWEEP_END=%#x SIGNAL=%d\n", b, WTERMSIG(st));
      else printf("SWEEP_END=%#x EXIT=%d\n", b, WEXITSTATUS(st));
      fflush(stdout);
    }
    printf("SWEEP_FUNCTIONS=%d\n", nfn);
    return 0;
  }
  if (strcmp(mode, "ctor")) return 0;
  for (int i = 0; i < nreg; i++) mprotect(regs[i].base, regs[i].len, PROT_READ | PROT_WRITE);
  for (int off = 0x290; off <= 0x298; off += 8) {
    uint64_t sp; memcpy(&sp, obj + off, 8);
    uint64_t buf = 0; uint32_t idx = 0, mask = 0;
    if (sp) { memcpy(&buf, (uint8_t *)sp + 4, 8); memcpy(&idx, (uint8_t *)sp + 0x10, 4); memcpy(&mask, (uint8_t *)sp + 0x14, 4); }
    printf("SUB_%X_NONNULL=%d BUF_NONNULL=%d IDX=%u MASK=%#x\n", off, sp != 0, buf != 0, idx, mask);
  }
  fflush(stdout);
  pid_t pid = fork();
  if (pid == 0) {
    float in[8] = {0.5f, -0.25f, 0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f}, out[16];
    memset(out, 0, sizeof out);
    ((FF)(img + strtoul(argv[3], 0, 16)))(obj, in, out, 4);
    _exit(0);
  }
  int st = 0; waitpid(pid, &st, 0);
  if (WIFSIGNALED(st)) printf("FRUITY_SIGNAL=%d\n", WTERMSIG(st));
  else printf("FRUITY_EXIT=%d\n", WEXITSTATUS(st));
  return 0;
}
