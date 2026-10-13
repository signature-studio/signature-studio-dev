// 参照実装 (native): win x64 Reverb.dll の *元の機械語* を RWX mmap し、gcc の ms_abi 関数ポインタで直接実行する。
// build: gcc -O1 -o native_ref native_ref.c   usage: native_ref image.bin ranges(fruity_rva uf_rva) cases.bin res_native.bin
// image.bin は locate.py が出す RVA 配置イメージ (rip 相対の定数参照は image 内で解決される。範囲内に reloc は無い)。
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
typedef void (__attribute__((ms_abi)) *FF)(void *, const float *, float *, uint32_t);
typedef void (__attribute__((ms_abi)) *FU)(void *, const float *, float *, float *, uint32_t);
#define NL 14
#define PTR0 0xbc
static uint32_t rd(FILE *f) { uint32_t v; if (fread(&v, 4, 1, f) != 1) { fprintf(stderr, "short read\n"); exit(2); } return v; }
int main(int argc, char **argv) {
  FILE *fi = fopen(argv[1], "rb"); fseek(fi, 0, SEEK_END); long isz = ftell(fi); rewind(fi);
  size_t map = (isz + 4095) & ~4095UL;
  uint8_t *img = mmap(0, map, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (img == MAP_FAILED) { perror("mmap"); return 2; }
  if (fread(img, 1, isz, fi) != (size_t)isz) return 2;
  uint32_t rva_f = strtoul(argv[2], 0, 16), rva_u = strtoul(argv[3], 0, 16);
  FILE *fc = fopen(argv[4], "rb"), *fo = fopen(argv[5], "wb");
  uint32_t ncase = rd(fc);
  for (uint32_t c = 0; c < ncase; c++) {
    uint32_t fn = rd(fc), n = rd(fc), aux = rd(fc), S = rd(fc), sz[NL], cap[NL];
    for (int i = 0; i < NL; i++) sz[i] = rd(fc);
    for (int i = 0; i < NL; i++) cap[i] = rd(fc);
    uint8_t *st = malloc(S); if (fread(st, 1, S, fc) != S) return 2;
    float *buf[NL]; size_t tot = 0;
    for (int i = 0; i < NL; i++) { buf[i] = malloc(cap[i] * 4); if (fread(buf[i], 4, cap[i], fc) != cap[i]) return 2; tot += cap[i]; }
    float *in = malloc(4 * (n + 1)); if (n && fread(in, 4, n, fc) != n) return 2;
    float *out = malloc(8 * (n + 1)), *ax = malloc(8 * (n + 1));
    memset(out, 0xA5, 8 * (n + 1)); memset(ax, 0xA5, 8 * (n + 1));
    for (int i = 0; i < NL; i++) { uint64_t p = (uint64_t)buf[i]; memcpy(st + PTR0 + 8 * i, &p, 8); }
    if (fn == 0) ((FF)(img + rva_f))(st, in, out, n);
    else ((FU)(img + rva_u))(st, in, out, aux ? ax : NULL, n);
    for (int i = 0; i < NL; i++) memset(st + PTR0 + 8 * i, 0, 8);   // ポインタ欄は runtime 依存なので 0 に正規化して書き出す
    fwrite(st, 1, S, fo);
    for (int i = 0; i < NL; i++) fwrite(buf[i], 4, cap[i], fo);
    fwrite(out, 4, 2 * n, fo);
    if (aux) fwrite(ax, 4, 2 * n, fo);
    free(st); for (int i = 0; i < NL; i++) free(buf[i]); free(in); free(out); free(ax);
  }
  fclose(fo); return 0;
}
