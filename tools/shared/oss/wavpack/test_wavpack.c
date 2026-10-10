/* WavPack 4.80.0 (wavpack_x64.dylib 実測 "4.80.0") 検証ハーネス。
 * native / wasm32 / wasm64 で同一入力を WV エンコード -> 復号して比較する。
 * FL は wavpack ライブラリを直接叩くため WavpackOpenFileOutput/SetConfiguration/
 *   PackSamples + OpenFileInput/UnpackSamples + MD5 sum の面を検証する。
 * usage: test_wavpack [out.wv] [-d in.wv]
 * 入力は libFLAC/libogg/LAME 検証と同じ libm 非依存 (共振器漸化式) PCM。
 * WavPack は lossless なので復号 PCM は入力と bit 一致するはず。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "wavpack.h"

#define NFRAMES 24000      /* ~0.54s @44100 stereo */
#define RATE 44100
#define CH 2

static void gen_pcm(int32_t *pcm, size_t n) {
  double x1 = 0.037, x2 = -0.021, yl = 0.0, yr = 0.013;
  uint64_t s = 88172645463325252ULL;
  for (size_t i = 0; i < n; i += 2) {
    s ^= s << 13; s ^= s >> 7; s ^= s << 17;
    double xn = ((double)(s >> 40) / 16777216.0) * 2.0 - 1.0;
    yl = 0.9821 * yl - 0.0179 * x1 + 0.0007 * x2 + xn * 0.31;
    yr = 0.9821 * yr - 0.0179 * x2 + 0.0007 * x1 + xn * 0.29;
    x2 = x1; x1 = xn;
    double vl = yl * 800000.0, vr = yr * 800000.0;
    if (vl > 8388607.0) vl = 8388607.0; if (vl < -8388608.0) vl = -8388608.0;
    if (vr > 8388607.0) vr = 8388607.0; if (vr < -8388608.0) vr = -8388608.0;
    pcm[i] = (int32_t)vl; pcm[i + 1] = (int32_t)vr;
  }
}
static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

/* ---- encoder (WavpackBlockOutput でバッファに集める: FILE* ではなく memcpy) ---- */
struct wv_out { unsigned char *buf; size_t len, cap; };
static struct wv_out *g_out;
static int wp_blockout(void *id, void *data, int32_t bcount) {
  (void)id;
  struct wv_out *o = g_out;
  if (o->len + bcount > o->cap) return 0;
  memcpy(o->buf + o->len, data, bcount); o->len += bcount;
  return 1;
}

static int do_encode(const int32_t *pcm, size_t frames, const char *path) {
  WavpackConfig cfg; memset(&cfg, 0, sizeof(cfg));
  cfg.bits_per_sample = 24;
  cfg.bytes_per_sample = 3;
  cfg.num_channels = CH;
  cfg.sample_rate = RATE;
  cfg.qmode = 0;
  cfg.flags = CONFIG_VERY_HIGH_FLAG;   /* 高圧縮既定 (pack.c:79) */
  unsigned char *buf = malloc(1 << 22);
  struct wv_out o = { buf, 0, 1 << 22 };
  g_out = &o;
  WavpackContext *wpc = WavpackOpenFileOutput(wp_blockout, NULL, NULL);
  if (!wpc) { fprintf(stderr, "open out fail\n"); return 1; }
  if (!WavpackSetConfiguration(wpc, &cfg, frames)) { fprintf(stderr, "setcfg fail\n"); return 1; }
  if (!WavpackPackInit(wpc)) { fprintf(stderr, "packinit fail\n"); return 1; }
  size_t left = frames;
  while (left) {
    uint32_t chunk = left > 48000 ? 48000 : left;
    if (!WavpackPackSamples(wpc, (int32_t *)&pcm[(frames - left) * CH], chunk)) {
      fprintf(stderr, "pack fail\n"); return 1;
    }
    left -= chunk;
  }
  if (!WavpackFlushSamples(wpc)) { fprintf(stderr, "flush fail\n"); return 1; }
  WavpackCloseFile(wpc);
  FILE *f = fopen(path, "wb"); if (!f) { perror("fopen out"); return 1; }
  fwrite(o.buf, 1, o.len, f); fclose(f);
  free(buf);
  printf("WV bytes=%zu\n", o.len);
  return 0;
}

static int do_decode(const char *path, const int32_t *ref, size_t refn) {
  char err[80] = "";
  WavpackContext *wpc = WavpackOpenFileInput(path, err, OPEN_WRAPPER | OPEN_TAGS, 0);
  if (!wpc) { fprintf(stderr, "open in fail: %s\n", err); return 1; }
  printf("WV version=%d rate=%lu bps=%d ch=%d numsamples=%lu\n",
         WavpackGetVersion(wpc), (unsigned long)WavpackGetSampleRate(wpc),
         WavpackGetBitsPerSample(wpc), WavpackGetNumChannels(wpc),
         (unsigned long)WavpackGetNumSamples(wpc));
  size_t cap = NFRAMES + 1024;
  int32_t *buf = malloc(cap * CH * sizeof(int32_t));
  size_t n = 0;
  while (1) {
    uint32_t got = WavpackUnpackSamples(wpc, buf + n * CH, (uint32_t)(cap - n));
    if (!got) break;
    n += got;
    if (n >= cap) break;
  }
  printf("DECODED samples=%zu hash=%016llx errs=%d\n", n * CH,
         (unsigned long long)fnv((const unsigned char *)buf, n * CH * sizeof(int32_t), 1469598103934665603ULL),
         WavpackGetNumErrors(wpc));
  size_t same = 0, tot = (refn * CH);
  for (size_t i = 0; i < tot; i++) if (buf[i] == ref[i]) same++;
  printf("WM identical %zu/%zu (reference frames=%zu)\n", same, tot, refn);
  WavpackCloseFile(wpc); free(buf);
  return (same == tot) ? 0 : 1;
}

int main(int argc, char **argv) {
  int32_t *pcm = malloc((size_t)NFRAMES * CH * sizeof(int32_t));
  gen_pcm(pcm, (size_t)NFRAMES * CH);
  uint64_t ph = fnv((const unsigned char *)pcm, (size_t)NFRAMES * CH * sizeof(int32_t), 1469598103934665603ULL);
  printf("PCM frames=%zu hash=%016llx\n", (size_t)NFRAMES, (unsigned long long)ph);
  const char *path = "out.wv"; int decode = 0;
  for (int i = 1; i < argc; i++) { if (!strcmp(argv[i], "-d")) { decode = 1; if (i+1 < argc) path = argv[i+1]; } else if (argv[i][0] != '-') path = argv[i]; }
  if (decode) return do_decode(path, pcm, NFRAMES);
  int rc = do_encode(pcm, NFRAMES, path);
  if (rc == 0) rc |= do_decode(path, pcm, NFRAMES);
  return rc;
}
