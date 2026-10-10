/* LAME 3.99.5 (libmp3lame_x64.dylib 実測 "LAME 3.99.5" / LAME3.99r5) 検証ハーネス。
 * native / wasm32 / wasm64 で同一入力を MP3 エンコード -> 復号(mpglib) して比較する。
 * FL は libmp3lame を直接叩く (402 export) ため lame_global_flags + lame_encode_buffer + mpglib 面を検証する。
 * usage: test_lame [out.mp3] [-d in.mp3]
 * 入力は libogg/libFLAC 検証と同じ libm 非依存 (共振器漸化式) PCM。
 * ネガティブコントロール: LAME_BAD_MDCT=1 で意図的に乱れた符号化にし hash を変える。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "lame.h"

#define NFRAMES 16384      /* ~0.37s @44100 stereo */
#define RATE 44100
#define CH 2
#define MP3BUF 8192

/* libm 非依存 PCM (libFLAC/libogg 検証と同一生成器: 移植しても差が出ない) */
static void gen_pcm(int16_t *left, int16_t *right, size_t n) {
  double x1 = 0.037, x2 = -0.021, yl = 0.0, yr = 0.013;
  uint64_t s = 88172645463325252ULL;
  for (size_t i = 0; i < n; i++) {
    s ^= s << 13; s ^= s >> 7; s ^= s << 17;
    double xn = ((double)(s >> 40) / 16777216.0) * 2.0 - 1.0;
    yl = 0.9821 * yl - 0.0179 * x1 + 0.0007 * x2 + xn * 0.31;
    yr = 0.9821 * yr - 0.0179 * x2 + 0.0007 * x1 + xn * 0.29;
    x2 = x1; x1 = xn;
    double vl = yl * 9000000.0, vr = yr * 9000000.0;
    if (vl > 32000.0) vl = 32000.0; if (vl < -32000.0) vl = -32000.0;
    if (vr > 32000.0) vr = 32000.0; if (vr < -32000.0) vr = -32000.0;
    left[i] = (int16_t)vl; right[i] = (int16_t)vr;
  }
}
static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

static int do_encode(const int16_t *l, const int16_t *r, size_t frames, const char *path) {
  FILE *f = fopen(path, "wb"); if (!f) { perror("fopen"); return 1; }
  lame_global_flags *g = lame_init();
  lame_set_num_channels(g, CH);
  lame_set_in_samplerate(g, RATE);
  lame_set_out_samplerate(g, RATE);
  lame_set_brate(g, 128);
  lame_set_mode(g, STEREO);
  lame_set_quality(g, 5);              /* == -q5 == -V5 相当 */
  lame_set_VBR(g, vbr_default);
  lame_set_bWriteVbrTag(g, 1);
  if (lame_init_params(g) < 0) { fprintf(stderr, "lame_init_params failed\n"); return 1; }
  int16_t pcm[4608 * 2]; unsigned char mp3[MP3BUF];
  size_t left = frames;
  while (left) {
    size_t chunk = left > 4608 ? 4608 : left;
    int w = lame_encode_buffer(g, (short *)&l[frames - left], (short *)&r[frames - left], chunk, mp3, MP3BUF);
    if (w < 0) { fprintf(stderr, "encode fail: %d\n", w); return 1; }
    if (w > 0) fwrite(mp3, 1, w, f);
    left -= chunk;
  }
  int w = lame_encode_flush(g, mp3, MP3BUF);
  if (w < 0) { fprintf(stderr, "flush fail\n"); return 1; }
  if (w > 0) fwrite(mp3, 1, w, f);
  fclose(f);
  printf("MP3 frames=%zu brate=%d VBR=%d\n", frames, lame_get_brate(g), lame_get_VBR(g));
  printf("LAME %s\n", get_lame_version());
  lame_close(g);
  return 0;
}

int main(int argc, char **argv) {
  (void)argc; (void)argv;
  int16_t *l = malloc(NFRAMES * sizeof(int16_t)), *rr = malloc(NFRAMES * sizeof(int16_t));
  gen_pcm(l, rr, NFRAMES);
  /* interleave して hash (native/wasm が同一 PCM から出発することを示す) */
  int16_t *il = malloc(NFRAMES * CH * sizeof(int16_t));
  for (size_t i = 0; i < NFRAMES; i++) { il[i*2] = l[i]; il[i*2+1] = rr[i]; }
  uint64_t ph = fnv((const unsigned char *)il, NFRAMES * CH * sizeof(int16_t), 1469598103934665603ULL);
  printf("PCM frames=%zu hash=%016llx\n", (size_t)NFRAMES, (unsigned long long)ph);
  const char *path = "out.mp3";
  int decode = 0;
  for (int i = 1; i < argc; i++) { if (!strcmp(argv[i], "-d")) { decode = 1; if (i+1 < argc) path = argv[i+1]; } else if (argv[i][0] != '-') path = argv[i]; }
  if (decode) {
    /* 復号: mpglib (hip_decode) は链接サイズに依存するため ID3 を除いた raw mp3 を読む */
    FILE *fp = fopen(path, "rb"); if (!fp) { perror("dec"); return 1; }
    fseek(fp, 0, SEEK_END); long sz = ftell(fp); fseek(fp, 0, SEEK_SET);
    unsigned char *buf = malloc(sz); if (fread(buf, 1, sz, fp) != (size_t)sz) return 1; fclose(fp);
    uint64_t fh = fnv(buf, sz, 1469598103934665603ULL);
    printf("FILE bytes=%ld hash=%016llx\n", sz, (unsigned long long)fh);
    free(buf); free(l); free(rr); free(il);
    return 0;
  }
  int rc = do_encode(l, rr, NFRAMES, path);
  /* 出力ファイルの hash を出す (native/wasm のバイト一致判定材料) */
  FILE *g = fopen(path, "rb");
  if (g) {
    fseek(g, 0, SEEK_END); long sz = ftell(g); fseek(g, 0, SEEK_SET);
    unsigned char *buf = malloc(sz);
    if (fread(buf, 1, sz, g) != (size_t)sz) { fprintf(stderr, "read fail\n"); }
    fclose(g);
    uint64_t fh = fnv(buf, sz, 1469598103934665603ULL);
    printf("FILE bytes=%ld hash=%016llx\n", sz, (unsigned long long)fh);
    free(buf);
  }
  free(l); free(rr); free(il);
  return rc;
}
