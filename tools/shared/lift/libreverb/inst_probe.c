// 実インスタンス probe: win Reverb.dll の CreateReverbInstance を元の機械語のまま ms_abi で実行し、返された状態を実測する。
// build: gcc -O1 -w -o inst_probe inst_probe.c   usage: inst_probe image.bin create_rva fruity_rva
// IAT は HeapAlloc / HeapFree の 2 件だけ C 実装 (calloc / free) に差し替える。他の IAT は 0 のまま (到達すれば SIGSEGV で見える)。
// Process_Fruity は fork した子で 1 回呼び、終了シグナルを記録する (親は落ちない)。
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/mman.h>
typedef void *(__attribute__((ms_abi)) *CRI)(void *);
typedef void (__attribute__((ms_abi)) *FF)(void *, const float *, float *, uint32_t);
#define NL 14
#define PTR0 0xbc
static void *__attribute__((ms_abi)) my_HeapAlloc(void *h, uint32_t fl, size_t n) { (void)h; (void)fl; return calloc(1, n ? n : 1); }
static int __attribute__((ms_abi)) my_HeapFree(void *h, uint32_t fl, void *p) { (void)h; (void)fl; free(p); return 1; }
int main(int argc, char **argv) {
  if (argc != 4) { fprintf(stderr, "usage: inst_probe image.bin create_rva fruity_rva\n"); return 2; }
  FILE *fi = fopen(argv[1], "rb"); if (!fi) return 2;
  fseek(fi, 0, SEEK_END); long isz = ftell(fi); rewind(fi);
  uint8_t *img = mmap(0, (isz + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (img == MAP_FAILED || fread(img, 1, isz, fi) != (size_t)isz) return 2;
  *(void **)(img + 0x60130) = (void *)my_HeapAlloc;   // KERNEL32 HeapAlloc の IAT slot
  *(void **)(img + 0x60138) = (void *)my_HeapFree;    // KERNEL32 HeapFree の IAT slot
  uint8_t *obj = ((CRI)(img + strtoul(argv[2], 0, 16)))(NULL);
  printf("CREATE_NONNULL=%d\n", obj != NULL);
  if (!obj) return 1;
  uint64_t vt; memcpy(&vt, obj, 8);
  printf("VPTR_RVA=%#lx\n", (unsigned long)((uint8_t *)vt - img));
  int nz = 0; for (int i = 0; i < 0x2a0; i++) nz += obj[i] != 0;
  printf("NONZERO_BYTES=%d\n", nz);
  int zero = 0;
  for (int i = 0; i < NL; i++) { uint64_t p; memcpy(&p, obj + PTR0 + 8 * i, 8); zero += p == 0; }
  printf("PTR14_ZERO=%d\n", zero);
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
