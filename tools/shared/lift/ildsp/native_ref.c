// 参照実装 (native): win x64 GeneralPitchShifter vtable slot 4 (RVA 0x1aa3a0) の *元の機械語* を RWX mmap し、ms_abi 関数ポインタで直接実行する。
// build: gcc -O1 -o native_ref native_ref.c   usage: native_ref fn.bin cases.bin res_native.bin
// cases.bin: u32 ncase, then per case: inner[0x2f8] + 5 buffers (64 dword each; ptr 欄の順 0x10,0x18,0x20,0x258,0x260) + wrapper[16]
// 出力 (per case, 固定 2060 B): u32 status(0) + inner[0x2f8] + wrapper[16] + 5 buffers。ポインタ欄 (inner 5 個) と wrapper+8 は 0 に正規化して書く。
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
typedef void (__attribute__((ms_abi)) *FN)(void *);
#define INNER 0x2f8
#define NB 5
#define BUFN 64
static const uint32_t PTR[NB] = {0x10, 0x18, 0x20, 0x258, 0x260};
static void rd(FILE *f, void *p, size_t n) { if (fread(p, 1, n, f) != n) { fprintf(stderr, "short read\n"); exit(2); } }
int main(int argc, char **argv) {
  FILE *ff = fopen(argv[1], "rb"); uint8_t code[0x100] = {0};
  size_t cn = fread(code, 1, sizeof code, ff); fclose(ff);
  uint8_t *img = mmap(0, 4096, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (img == MAP_FAILED) { perror("mmap"); return 2; }
  memcpy(img, code, cn);
  FILE *fc = fopen(argv[2], "rb"), *fo = fopen(argv[3], "wb");
  uint32_t ncase; rd(fc, &ncase, 4);
  for (uint32_t c = 0; c < ncase; c++) {
    uint8_t *inner = malloc(INNER), *wrap = malloc(16);
    uint32_t *buf[NB];
    rd(fc, inner, INNER);
    for (int i = 0; i < NB; i++) { buf[i] = malloc(BUFN * 4); rd(fc, buf[i], BUFN * 4); }
    rd(fc, wrap, 16);
    for (int i = 0; i < NB; i++) { uint64_t p = (uint64_t)buf[i]; memcpy(inner + PTR[i], &p, 8); }
    uint64_t ip = (uint64_t)inner; memcpy(wrap + 8, &ip, 8);
    ((FN)img)(wrap);
    for (int i = 0; i < NB; i++) memset(inner + PTR[i], 0, 8);
    memset(wrap + 8, 0, 8);
    uint32_t st = 0;
    fwrite(&st, 4, 1, fo); fwrite(inner, 1, INNER, fo); fwrite(wrap, 1, 16, fo);
    for (int i = 0; i < NB; i++) fwrite(buf[i], 4, BUFN, fo);
    free(inner); free(wrap); for (int i = 0; i < NB; i++) free(buf[i]);
  }
  fclose(fc); fclose(fo); return 0;
}
