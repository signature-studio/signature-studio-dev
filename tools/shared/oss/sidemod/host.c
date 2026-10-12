/* side module ローダ兼テスト host (MAIN_MODULE)。
 * FL 由来コードを含まない。dlopen のパスを差し替えるだけで別ビルドの
 * ffmpeg.so / lame.so に入れ替えられること (LGPL-2.1 §6(b) 論点の PoC) を示す。
 * usage: host <ffmpeg.so> <lame.so> <out.mp3> <input> ...
 * 出力: SIDE ... / LAME ... / DECODE ... 行 (e2e.sh が native 基準値と突合する) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <dlfcn.h>

typedef struct { int channels, rate; long long frames, samples; unsigned long long pcm_hash; char codec[32]; } ss_ff_info;

static void *must(void *lib, const char *name) {
  void *p = dlsym(lib, name);
  if (!p) { fprintf(stderr, "dlsym %s: %s\n", name, dlerror()); exit(3); }
  return p;
}
static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

int main(int argc, char **argv) {
  if (argc < 5) { fprintf(stderr, "usage: host ffmpeg.so lame.so out.mp3 in...\n"); return 2; }
  void *ff = dlopen(argv[1], RTLD_NOW), *lm = dlopen(argv[2], RTLD_NOW);
  if (!ff) { fprintf(stderr, "dlopen %s: %s\n", argv[1], dlerror()); return 3; }
  if (!lm) { fprintf(stderr, "dlopen %s: %s\n", argv[2], dlerror()); return 3; }

  int (*ff_abi)(void) = must(ff, "ss_abi_version");
  const char *(*ff_lic)(void) = must(ff, "ss_ff_license");
  const char *(*ff_cfg)(void) = must(ff, "ss_ff_configuration");
  int (*ff_ssz)(void) = must(ff, "ss_ff_struct_size");
  int (*ff_dec)(const char *, ss_ff_info *) = must(ff, "ss_ff_decode");
  int (*lm_abi)(void) = must(lm, "ss_abi_version");
  const char *(*lm_ver)(void) = must(lm, "ss_lame_version");
  void *(*lm_open)(int, int, int, int) = must(lm, "ss_lame_open");
  int (*lm_enc)(void *, short *, short *, int, unsigned char *, int) = must(lm, "ss_lame_encode");
  int (*lm_flush)(void *, unsigned char *, int) = must(lm, "ss_lame_flush");
  void (*lm_close)(void *) = must(lm, "ss_lame_close");

  if (ff_ssz() != (int)sizeof(ss_ff_info)) { fprintf(stderr, "ABI struct size mismatch\n"); return 4; }
  printf("SIDE ffmpeg abi=%d license=\"%s\"\n", ff_abi(), ff_lic());
  printf("SIDE ffmpeg configuration=%s\n", ff_cfg());
  printf("SIDE lame abi=%d version=%s\n", lm_abi(), lm_ver());

  /* LAME: libm 非依存 PCM (oss/lame/test_lame.c と同一生成器・同一パラメータ) を MP3 化 */
  enum { N = 16384 };
  short *l = malloc(N * 2), *r = malloc(N * 2);
  double x1 = 0.037, x2 = -0.021, yl = 0.0, yr = 0.013; uint64_t s = 88172645463325252ULL;
  for (int i = 0; i < N; i++) {
    s ^= s << 13; s ^= s >> 7; s ^= s << 17;
    double xn = ((double)(s >> 40) / 16777216.0) * 2.0 - 1.0;
    yl = 0.9821 * yl - 0.0179 * x1 + 0.0007 * x2 + xn * 0.31;
    yr = 0.9821 * yr - 0.0179 * x2 + 0.0007 * x1 + xn * 0.29;
    x2 = x1; x1 = xn;
    double vl = yl * 9000000.0, vr = yr * 9000000.0;
    if (vl > 32000.0) vl = 32000.0;
    if (vl < -32000.0) vl = -32000.0;
    if (vr > 32000.0) vr = 32000.0;
    if (vr < -32000.0) vr = -32000.0;
    l[i] = (short)vl; r[i] = (short)vr;
  }
  void *g = lm_open(44100, 2, 128, 5);
  if (!g) { fprintf(stderr, "ss_lame_open failed\n"); return 5; }
  FILE *f = fopen(argv[3], "wb"); if (!f) { perror("fopen"); return 6; }
  unsigned char mp3[8192]; uint64_t h = 1469598103934665603ULL; long total = 0;
  for (int off = 0; off < N; ) {
    int c = N - off > 4608 ? 4608 : N - off;
    int w = lm_enc(g, l + off, r + off, c, mp3, sizeof mp3);
    if (w < 0) { fprintf(stderr, "encode %d\n", w); return 7; }
    fwrite(mp3, 1, w, f); h = fnv(mp3, w, h); total += w; off += c;
  }
  int w = lm_flush(g, mp3, sizeof mp3);
  if (w < 0) return 8;
  fwrite(mp3, 1, w, f); h = fnv(mp3, w, h); total += w; fclose(f); lm_close(g);
  printf("LAME bytes=%ld stream_hash=%016llx\n", total, (unsigned long long)h);

  for (int i = 4; i < argc; i++) {
    ss_ff_info info; memset(&info, 0, sizeof info);
    int rc = ff_dec(argv[i], &info);
    if (rc) { printf("DECODE %s: error=%d\n", argv[i], rc); continue; }
    printf("DECODE %s: codec=%s ch=%d rate=%d frames=%lld samples=%lld pcm_hash=%016llx\n",
           argv[i], info.codec, info.channels, info.rate, info.frames, info.samples, info.pcm_hash);
  }
  return 0;
}
