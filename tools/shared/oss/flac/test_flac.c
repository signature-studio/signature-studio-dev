/* libFLAC 検証ハーネス (native / wasm32 / wasm64 で同一入力を round-trip して出力を比較する)。
 * FL の EasyFLAC / oggio が使う API 面: stream_encoder + stream_decoder + metadata + MD5。
 *   1) version 出力 (FLAC_API_VERSION_* / libFLAC の runtime version)
 *   2) PCM(libm 非依存パターン) -> FLAC エンコード -> 復号 -> PCM 一致
 *   3) 各ステップの hash / byte 数を出力
 * usage: test_flac [out.flac] [-d in.flac]
 * 入力生成は libogg 検証と同じ libm 非依存 (共振器漸化式) で native/wasm 間の差を排除する。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include "FLAC/stream_encoder.h"
#include "FLAC/stream_decoder.h"
#include "FLAC/metadata.h"

#define NFRAMES 11025   /* 0.25 s @ 44100 */
#define RATE 44100
#define NCH 2

static void gen_pcm(int32_t *pcm, size_t n) {
  double x1 = 0.037, x2 = -0.021, y = 0.0;
  uint64_t s = 88172645463325252ULL;
  for (size_t i = 0; i < n; i++) {
    s ^= s << 13; s ^= s >> 7; s ^= s << 17;
    double xn = ((double)(s >> 40) / 16777216.0) * 2.0 - 1.0;
    y = 0.9821 * y - 0.0179 * x1 + 0.0007 * x2 + xn * 0.31;
    x2 = x1; x1 = xn;
    double v = y * 4000000.0;
    /* 24bit (bps=24) では sample_max = INT32_MAX>>8 = 8388607。はみ出した値は
     * libFLAC が CLIENT_ERROR を返す (stream_encoder.c: sample_min/max 検証) ので
     * 生成時に範囲内へクランプする。丸めではなく飽和なので native/wasm で同値 */
    if (v > 8388607.0) v = 8388607.0; if (v < -8388608.0) v = -8388608.0;
    pcm[i] = (int32_t)v;
  }
}

static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

static void print_version(void) {
  printf("FLAC_API_VERSION_CURRENT=%d\n", FLAC_API_VERSION_CURRENT);
  /* ライブラリの build 時 version は config.h の PACKAGE_VERSION (=configure で決定) */
#ifdef PACKAGE_VERSION
  printf("PACKAGE_VERSION=%s\n", PACKAGE_VERSION);
#endif
#if defined(FLAC__HAS_X86INTRIN)
  printf("x86intrin=1\n");
#else
  printf("x86intrin=0\n");
#endif
#if defined(FLAC__HAS_OGG)
  printf("has_ogg=1\n");
#else
  printf("has_ogg=0\n");
#endif
}

/* ---- encoder ---- */
/* libFLAC 付属の init_FILE を使う (FLAC__stream_encoder_init_FILE) — write/seek/tell は libFLAC 内部で解決 */

static size_t left_off(const int32_t *pcm, size_t frames, size_t left) {
  (void)pcm; return frames - left;
}
static int g_dec_errors = 0;

static int do_encode(const int32_t *pcm, size_t frames, const char *path) {
  FILE *f = fopen(path, "wb"); if (!f) { perror("fopen"); return 1; }
  FLAC__StreamEncoder *e = FLAC__stream_encoder_new();
  FLAC__stream_encoder_set_channels(e, NCH);
  FLAC__stream_encoder_set_bits_per_sample(e, 24);
  FLAC__stream_encoder_set_sample_rate(e, RATE);
  FLAC__stream_encoder_set_compression_level(e, 5);
  FLAC__stream_encoder_set_streamable_subset(e, true);
  FLAC__stream_encoder_set_verify(e, false);
#if FLAC_API_VERSION_CURRENT >= 14
  FLAC__stream_encoder_set_num_threads(e, 1);  /* 1.5.0 以降のみ存在 (1.3.1 は未対応) */
#endif
  FLAC__stream_encoder_set_do_mid_side_stereo(e, true);
  FLAC__stream_encoder_set_loose_mid_side_stereo(e, false);
  FLAC__stream_encoder_set_apodization(e, "tukey(0.5)");
  FLAC__stream_encoder_set_max_lpc_order(e, 12);
  FLAC__stream_encoder_set_blocksize(e, 4096);
  /* blocksize を明示 0 に戻す (1152 に上げたのは実験) し total_samples_estimate を 0 (不明) にすると
     FLAC は STREAMINFO に total を unknown として書く。頼るべきは blocksize 設定のみ */
  FLAC__stream_encoder_set_blocksize(e, 0);
  FLAC__stream_encoder_set_total_samples_estimate(e, 0);
  FLAC__StreamEncoderInitStatus est = FLAC__stream_encoder_init_FILE(e, f, NULL, NULL);
  if (est != FLAC__STREAM_ENCODER_INIT_STATUS_OK) {
    fprintf(stderr, "enc init failed: status=%d\n", (int)est); return 1;
  }
    size_t left = frames;
  while (left) {
    size_t chunk = left > 4096 ? 4096 : left;
  if (!FLAC__stream_encoder_process_interleaved(e, (const FLAC__int32 *)&pcm[left_off(pcm, frames, left) * NCH], chunk)) {
    fprintf(stderr, "encoder state: %s (resolved: %s)\n", FLAC__StreamEncoderStateString[FLAC__stream_encoder_get_state(e)],
            FLAC__stream_encoder_get_resolved_state_string(e)); return 1;
  }
    left -= chunk;
  }
  if (!FLAC__stream_encoder_finish(e)) { fprintf(stderr, "finish fail: %s\n", FLAC__StreamEncoderStateString[FLAC__stream_encoder_get_state(e)]); return 1; }
  fprintf(stderr, "[encode] frames=%zu->FLAC\n", frames);
  FLAC__stream_encoder_delete(e);  /* finish() が FILE を既に閉じる */
  /* metadata 経由で STREAMINFO の内容を示す (blocksize / MD5 等) */
  FLAC__StreamMetadata *md = NULL;
  if (!FLAC__metadata_get_tags(path, &md) || !md) return 1;
  uint64_t h = fnv((const unsigned char *)&md->data.stream_info, sizeof(md->data.stream_info), 1469598103934665603ULL);
  printf("STREAMINFO hash=%016llx minblk=%u maxblk=%u maxframe=%llu\n", (unsigned long long)h,
         md->data.stream_info.min_blocksize, md->data.stream_info.max_blocksize,
         (unsigned long long)md->data.stream_info.max_framesize);
  FLAC__metadata_object_delete(md);
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
  return 0;
}

/* ---- decoder ---- */
struct dec_buf { int32_t *pcm; size_t n, cap; FILE *f; };
static FLAC__StreamDecoderWriteStatus dec_w(const FLAC__StreamDecoder *d, const FLAC__Frame *fr, const FLAC__int32 *const buf[], void *cd) {
  (void)d; struct dec_buf *b = cd;
  for (unsigned i = 0; i < fr->header.blocksize; i++) {
    if (b->n < b->cap) { b->pcm[b->n * NCH] = buf[0][i]; b->pcm[b->n * NCH + 1] = buf[1][i]; }
    b->n++;
  }
  return FLAC__STREAM_DECODER_WRITE_STATUS_CONTINUE;
}
static FLAC__StreamDecoderReadStatus dec_r(const FLAC__StreamDecoder *d, FLAC__byte buf[], size_t *b, void *cd) {
  (void)d; struct dec_buf *s = cd; *b = fread(buf, 1, *b, s->f);
  return *b ? FLAC__STREAM_DECODER_READ_STATUS_CONTINUE : FLAC__STREAM_DECODER_READ_STATUS_END_OF_STREAM;
}
static FLAC__StreamDecoderSeekStatus dec_s(const FLAC__StreamDecoder *d, FLAC__uint64 off, void *cd) {
  (void)d; struct dec_buf *s = cd; if (fseek(s->f, (long)off, SEEK_SET)) return FLAC__STREAM_DECODER_SEEK_STATUS_ERROR; return FLAC__STREAM_DECODER_SEEK_STATUS_OK;
}
static FLAC__StreamDecoderTellStatus dec_t(const FLAC__StreamDecoder *d, FLAC__uint64 *off, void *cd) {
  (void)d; struct dec_buf *s = cd; long p = ftell(s->f); if (p < 0) return FLAC__STREAM_DECODER_TELL_STATUS_ERROR; *off = (FLAC__uint64)p; return FLAC__STREAM_DECODER_TELL_STATUS_OK;
}
static FLAC__StreamDecoderLengthStatus dec_l(const FLAC__StreamDecoder *d, FLAC__uint64 *off, void *cd) {
  (void)d; struct dec_buf *s = cd; fseek(s->f, 0, SEEK_END); *off = (FLAC__uint64)ftell(s->f); fseek(s->f, 0, SEEK_SET); return FLAC__STREAM_DECODER_LENGTH_STATUS_OK;
}
static void dec_e(const FLAC__StreamDecoder *d, FLAC__StreamDecoderErrorStatus st, void *cd) {
  (void)d; (void)cd; g_dec_errors++;
  fprintf(stderr, "decoder error: %s\n", FLAC__StreamDecoderErrorStatusString[st]);
}
static void dec_m(const FLAC__StreamDecoder *d, const FLAC__StreamMetadata *md, void *cd) {
  printf("METADATA type=%d last=%d len=%u\n", md->type, md->is_last, md->length);
  if (md->type == FLAC__METADATA_TYPE_STREAMINFO) {
    const FLAC__StreamMetadata_StreamInfo *si = &md->data.stream_info;
    printf("STREAMINFO_DEC minblk=%u maxblk=%u rate=%u ch=%u bps=%u total=%llu\n",
           si->min_blocksize, si->max_blocksize, si->sample_rate, si->channels, si->bits_per_sample,
           (unsigned long long)si->total_samples);
  }
}
static int do_decode(const char *path, const int32_t *ref, size_t refn) {
  FILE *f = fopen(path, "rb"); if (!f) { perror("fopen dec"); return 1; }
  FLAC__StreamDecoder *d = FLAC__stream_decoder_new();
  struct dec_buf b = { 0, 0, 0, f };
  size_t cap = NFRAMES + 64;
  b.pcm = malloc(cap * NCH * sizeof(int32_t)); b.cap = cap;
  FLAC__stream_decoder_set_md5_checking(d, true);
  FLAC__stream_decoder_set_metadata_respond_all(d);
  FLAC__StreamDecoderInitStatus st = FLAC__stream_decoder_init_FILE(d, f, dec_w, dec_m, dec_e, &b);
  if (st != FLAC__STREAM_DECODER_INIT_STATUS_OK) { fprintf(stderr, "dec init %d\n", st); return 1; }
  if (!FLAC__stream_decoder_process_until_end_of_stream(d)) {
    fprintf(stderr, "dec state: %s\n", FLAC__StreamDecoderStateString[FLAC__stream_decoder_get_state(d)]); return 1;
  }
  FLAC__stream_decoder_delete(d);  /* finish() が FILE を既に閉じる */
  uint64_t h = fnv((const unsigned char *)b.pcm, b.n * NCH * sizeof(int32_t), 1469598103934665603ULL);
  printf("DECODED frames=%zu cap=%zu hash=%016llx errors=%d\n", b.n, cap, (unsigned long long)h, g_dec_errors);
  size_t same = 0, n = (refn < b.n ? refn : b.n) * NCH;
  for (size_t i = 0; i < n; i++) if (ref[i] == b.pcm[i]) same++;
  printf("PCM identical %zu/%zu (reference frames=%zu)\n", same, n, refn);
  free(b.pcm);
  return (same == n && refn == b.n && g_dec_errors == 0) ? 0 : 1;
}

int main(int argc, char **argv) {
  print_version();
  const char *path = "out.flac";
  int decode_mode = 0;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "-d")) { decode_mode = 1; if (i + 1 < argc) path = argv[i + 1]; }
    else if (argv[i][0] != '-') path = argv[i];
  }
  int32_t *pcm = malloc((size_t)NFRAMES * NCH * sizeof(int32_t));
  gen_pcm(pcm, (size_t)NFRAMES * NCH);
  uint64_t ph = fnv((const unsigned char *)pcm, (size_t)NFRAMES * NCH * sizeof(int32_t), 1469598103934665603ULL);
  printf("PCM frames=%zu hash=%016llx\n", (size_t)NFRAMES, (unsigned long long)ph);
  if (decode_mode) return do_decode(path, pcm, NFRAMES);
  int rc = do_encode(pcm, NFRAMES, path);
  rc |= do_decode(path, pcm, NFRAMES);
  free(pcm);
  return rc;
}
