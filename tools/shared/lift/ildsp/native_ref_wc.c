// 参照実装 (native): ildsp (block24360_PE.bin) の WaveformColouring_CreateInstance (0x1ac470) と、その確保失敗 path を
// 元の機械語のまま実行する。PE は ImageBase (0x180000000) に固定配置し、IAT は stub (呼ばれた番号を記録して dispatch へ jmp) に差し替える。
// 到達の記録は int3 (元の 1 byte を退避して 0xCC にし、trap で記録して 1 命令だけ単歩して書き戻す)。
// build: gcc -O1 -no-pie -o native_ref native_ref_wc.c
// usage: native_ref image.bin iat.txt        (両方 native_image.py の出力)
// 出力: 1 行 1 件の `key value`。ケースは normal (HeapAlloc 成功)・alloc_fail (HeapAlloc が NULL)・alloc_m1 (0x1ac9c0 を size=-1 で直接呼ぶ)。
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <signal.h>
#include <setjmp.h>
#include <sys/mman.h>
#include <ucontext.h>

#define IMAGE_BASE 0x180000000ULL
#define SZ_IMAGE 0x447000UL
#define MAXIAT 128
#define NBP 12
#define STUB_SZ 32
#define HEAP_LOOP_MAX 1000

typedef uint64_t (__attribute__((ms_abi)) *FN0)(void);
typedef uint64_t (__attribute__((ms_abi)) *FN1)(uint64_t);

struct bp {
  uint32_t rva;
  const char *what;
  uint8_t orig;
  int hits;
  uint64_t rcx, rax, rsp, ret;
};

static uint8_t *img, *stubs;
static volatile int g_slot;
static char iat_name[MAXIAT][96];
static uint32_t iat_rva[MAXIAT];
static int n_iat;
static int iat_hits[MAXIAT];
static struct bp bps[NBP] = {
  {0x1ac4b4, "store vptr (WC instance, rcx=instance)"},
  {0x1ac9c0, "alloc entry (rcx=size)"},
  {0x1ac9ea, "alloc: after new handler, rbx!=-1 falls to throw"},
  {0x1b6f4c, "new handler (alloc failed)"},
  {0x1ad008, "throw path A entry (rbx!=-1)"},
  {0x1acfe8, "store fn A entry"},
  {0x1acfff, "store vptr 0x3d2778 (exception object)"},
  {0x1ad028, "throw path B entry (rbx==-1)"},
  {0x164740, "store fn B entry"},
  {0x16475a, "store vptr 0x3d27a0 (exception object)"},
  {0x1acfe0, "stub 0x1acfe0 (jmp 0x1801b34a8, no vptr store)"},
  {0x1cb5e0, "new handler thunk (jmp rax; rax := harness stub returning 0)"},
};
static struct bp helper = {0x1aedc0, "helper 0x1aedc0 (throw, RaiseException 前)"};

static volatile int rearm = -1;   /* 単歩の後に書き戻す bp (bps の添字。-2 は helper) */
static sigjmp_buf jb;
static const char *stop_why = "";
static uint64_t stop_rip;
static int heap_fail;
static int heap_calls;
static uint64_t exc_args[4];
static uint64_t exc_code;
static uint64_t last_ret;

static int find_iat(const char *suffix) {
  for (int i = 0; i < n_iat; i++) {
    size_t n = strlen(iat_name[i]), m = strlen(suffix);
    if (n >= m && !strcmp(iat_name[i] + n - m, suffix)) return i;
  }
  return -1;
}

static uint64_t __attribute__((ms_abi)) dispatch(uint64_t a, uint64_t b, uint64_t c, uint64_t d) {
  int s = g_slot;
  iat_hits[s]++;
  const char *nm = iat_name[s];
  if (!strcmp(nm, "KERNEL32.dll!HeapAlloc")) {
    heap_calls++;
    if (heap_calls > HEAP_LOOP_MAX) { stop_why = "HeapAlloc loop"; siglongjmp(jb, 1); }
    if (heap_fail) return 0;
    return (uint64_t)calloc(1, c);
  }
  if (!strcmp(nm, "KERNEL32.dll!GetProcessHeap")) return 0x1000;
  if (!strcmp(nm, "KERNEL32.dll!HeapFree")) { free((void *)c); return 1; }
  if (!strcmp(nm, "KERNEL32.dll!RtlPcToFileHeader")) return IMAGE_BASE;
  if (!strcmp(nm, "KERNEL32.dll!RaiseException")) {
    exc_code = a;
    /* 引数: a=code, b=flags, c=nargs, d=ExceptionInformation (*ULONG_PTR) */
    if (d) for (int i = 0; i < 4; i++) exc_args[i] = ((uint64_t *)d)[i];
    stop_why = "RaiseException";
    siglongjmp(jb, 1);
  }
  return 0;
}

static void make_stub(int i) {
  uint8_t *p = stubs + i * STUB_SZ;
  uint32_t addr32 = (uint32_t)(uintptr_t)&g_slot, v = (uint32_t)i;
  uint64_t h = (uint64_t)(uintptr_t)dispatch;
  p[0] = 0xC7; p[1] = 0x04; p[2] = 0x25;          /* mov dword ptr [addr32], i */
  memcpy(p + 3, &addr32, 4); memcpy(p + 7, &v, 4);
  p[11] = 0x49; p[12] = 0xBB;                     /* movabs r11, dispatch */
  memcpy(p + 13, &h, 8);
  p[21] = 0x41; p[22] = 0xFF; p[23] = 0xE3;       /* jmp r11 */
}

static void arm(struct bp *b) { img[b->rva] = 0xCC; }

static void on_fault(int sig, siginfo_t *si, void *ctx_) {
  ucontext_t *uc = ctx_;
  greg_t *g = uc->uc_mcontext.gregs;
  if (sig == SIGTRAP && rearm != -1) {
    /* 単歩の完了: bp を戻し、TF を下ろす */
    if (rearm == -2) img[helper.rva] = 0xCC; else img[bps[rearm].rva] = 0xCC;
    rearm = -1;
    g[REG_EFL] &= ~0x100;
    return;
  }
  uint64_t rip = g[REG_RIP];
  if (sig == SIGTRAP) {
    struct bp *hit = NULL; int k = -1;
    for (int i = 0; i < NBP; i++) if (IMAGE_BASE + bps[i].rva == rip - 1) { hit = &bps[i]; k = i; }
    if (rip - 1 == IMAGE_BASE + helper.rva) { hit = &helper; k = -2; }
    if (!hit) { stop_why = "unexpected trap"; stop_rip = rip; siglongjmp(jb, 1); }
    hit->hits++;
    if (hit->hits == 1) {
      hit->rcx = g[REG_RCX]; hit->rax = g[REG_RAX]; hit->rsp = g[REG_RSP];
      hit->ret = *(uint64_t *)(uintptr_t)g[REG_RSP];
    }
    if (hit->rva == 0x1cb5e0) g[REG_RAX] = (greg_t)(uintptr_t)(stubs + n_iat * STUB_SZ);
    img[hit->rva] = hit->orig;
    g[REG_RIP] = rip - 1;
    g[REG_EFL] |= 0x100;
    rearm = k;
    return;
  }
  stop_why = sig == SIGSEGV ? "SIGSEGV" : "signal";
  stop_rip = rip;
  siglongjmp(jb, 1);
}

static void rva_str(const char *lbl, uint64_t va) {
  printf("%s %#llx\n", lbl, (unsigned long long)(va - IMAGE_BASE));
}

static void print_bp(const struct bp *b) {
  printf("bp %#x hits %d %s\n", b->rva, b->hits, b->what);
  if (!b->hits) return;
  long long d = (long long)(b->rcx - b->rsp);
  if (d > -0x10000 && d < 0x10000) printf("  first rcx stack rsp%+lld\n", d);
  else printf("  first rcx not stack\n");
  if (b->rax >= IMAGE_BASE && b->rax < IMAGE_BASE + SZ_IMAGE) printf("  first rax_rva %#llx\n", (unsigned long long)(b->rax - IMAGE_BASE));
  if (b->ret >= IMAGE_BASE && b->ret < IMAGE_BASE + SZ_IMAGE) printf("  first caller_rva %#llx\n", (unsigned long long)(b->ret - IMAGE_BASE));
}

static void reset_state(void) {
  for (int i = 0; i < NBP; i++) { bps[i].hits = 0; arm(&bps[i]); }
  helper.hits = 0;
  arm(&helper);
  memset(iat_hits, 0, sizeof iat_hits);
  heap_calls = 0; stop_why = ""; stop_rip = 0; rearm = -1; exc_code = 0; memset(exc_args, 0, sizeof exc_args);
}

enum { C_NORMAL, C_ALLOC_FAIL, C_ALLOC_M1 };

static void run_case(const char *name, int kind) {
  reset_state();
  heap_fail = kind == C_ALLOC_FAIL;
  last_ret = 0;
  if (sigsetjmp(jb, 1) == 0) {
    if (kind == C_ALLOC_M1) last_ret = ((FN1)(img + 0x1ac9c0))((uint64_t)-1);
    else last_ret = ((FN0)(img + 0x1ac470))();
    stop_why = "returned";
  }
  printf("== case %s\n", name);
  printf("stop %s\n", stop_why);
  if (stop_rip) rva_str("stop_rip", stop_rip);
  printf("ret %s\n", last_ret ? "non-null" : "null");
  if (kind == C_NORMAL && last_ret) {
    uint64_t vptr = *(uint64_t *)(uintptr_t)last_ret;
    rva_str("instance_vptr_rva", vptr);
    printf("instance_vptr_is_WC %d\n", vptr == IMAGE_BASE + 0x3e01b0);
    rva_str("wc_slot3_value_rva", *(uint64_t *)(img + 0x3e01c8));
  }
  printf("heap_alloc_calls %d\n", heap_calls);
  for (int i = 0; i < NBP; i++) print_bp(&bps[i]);
  print_bp(&helper);
  if (exc_code) {
    printf("RaiseException code %#llx args[0] %#llx\n", (unsigned long long)exc_code, (unsigned long long)exc_args[0]);
    printf("RaiseException args[0] is 0x19930520 %d\n", exc_args[0] == 0x19930520ULL);
  }
  for (int i = 0; i < n_iat; i++) if (iat_hits[i]) printf("import %s %d\n", iat_name[i], iat_hits[i]);
}

int main(int argc, char **argv) {
  if (argc != 3) { fprintf(stderr, "usage: %s image.bin iat.txt\n", argv[0]); return 2; }
  FILE *fi = fopen(argv[1], "rb");
  if (!fi) { perror("image"); return 2; }
  uint8_t *raw = malloc(SZ_IMAGE);
  if (fread(raw, 1, SZ_IMAGE, fi) != SZ_IMAGE) { fprintf(stderr, "short image\n"); return 2; }
  fclose(fi);
  img = mmap((void *)IMAGE_BASE, SZ_IMAGE, PROT_READ | PROT_WRITE | PROT_EXEC,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  if (img == MAP_FAILED || (uint64_t)(uintptr_t)img != IMAGE_BASE) { perror("mmap ImageBase"); return 2; }
  memcpy(img, raw, SZ_IMAGE);
  free(raw);

  FILE *ft = fopen(argv[2], "r");
  if (!ft) { perror("iat"); return 2; }
  char line[256];
  while (n_iat < MAXIAT && fgets(line, sizeof line, ft)) {
    unsigned rva; char nm[96];
    if (sscanf(line, "%x %95s", &rva, nm) != 2) continue;
    iat_rva[n_iat] = rva; snprintf(iat_name[n_iat], sizeof iat_name[0], "%s", nm); n_iat++;
  }
  fclose(ft);

  stubs = mmap(NULL, 4096, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (stubs == MAP_FAILED) { perror("mmap stubs"); return 2; }
  if ((uintptr_t)&g_slot > 0x7fffffffUL) { fprintf(stderr, "g_slot above 2 GiB\n"); return 2; }
  strcpy(iat_name[n_iat], "harness!new_handler");
  for (int i = 0; i <= n_iat; i++) {
    make_stub(i);
    uint64_t a = (uint64_t)(uintptr_t)(stubs + i * STUB_SZ);
    if (i < n_iat) memcpy(img + iat_rva[i], &a, 8);
  }

  for (int i = 0; i < NBP; i++) bps[i].orig = img[bps[i].rva];
  helper.orig = img[helper.rva];

  struct sigaction sa;
  memset(&sa, 0, sizeof sa);
  sa.sa_sigaction = on_fault;
  sa.sa_flags = SA_SIGINFO | SA_NODEFER;
  sigaction(SIGTRAP, &sa, NULL);
  sigaction(SIGSEGV, &sa, NULL);

  printf("image %s base %#llx size %#lx imports %d\n", argv[1], (unsigned long long)IMAGE_BASE, SZ_IMAGE, n_iat);
  run_case("normal", C_NORMAL);
  run_case("alloc_fail", C_ALLOC_FAIL);
  run_case("alloc_m1", C_ALLOC_M1);
  return 0;
}
