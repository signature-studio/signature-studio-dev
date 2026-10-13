/* libFLAC 1.5.0 メモリ→メモリ復号ラッパ (wasm32)。
 *   fd_decode(in, n)  -> 0 = 成功 (MD5 検証込み) / 1 = 復号エラー / 2 = MD5 不一致 / 3 = ストリーム異常
 *   成功後 fd_pcm() (int32 先頭ポインタ) / fd_pcm_samples() (要素数) で interleaved int32 PCM、fd_rate/fd_channels/fd_bps/fd_total_lo/fd_total_hi/fd_has_md5/fd_md5 で属性
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "FLAC/stream_decoder.h"

typedef struct {
  const uint8_t *in;
  size_t n, pos;
  int32_t *pcm;
  size_t cap, len; /* int32 要素数 */
  uint32_t rate, ch, bps;
  uint64_t total;
  int has_md5;
  uint8_t md5[16];
  int err;
} Ctx;

static Ctx g;

static FLAC__StreamDecoderReadStatus rd(const FLAC__StreamDecoder *d, FLAC__byte buf[], size_t *bytes, void *c) {
  (void)d; (void)c;
  size_t left = g.n - g.pos;
  if (left == 0) { *bytes = 0; return FLAC__STREAM_DECODER_READ_STATUS_END_OF_STREAM; }
  size_t k = *bytes < left ? *bytes : left;
  memcpy(buf, g.in + g.pos, k);
  g.pos += k;
  *bytes = k;
  return FLAC__STREAM_DECODER_READ_STATUS_CONTINUE;
}

static FLAC__StreamDecoderWriteStatus wr(const FLAC__StreamDecoder *d, const FLAC__Frame *f, const FLAC__int32 *const buf[], void *c) {
  (void)d; (void)c;
  size_t need = (size_t)f->header.blocksize * f->header.channels;
  if (g.len + need > g.cap) {
    size_t nc = g.cap ? g.cap * 2 : (1u << 20);
    while (nc < g.len + need) nc *= 2;
    int32_t *p = (int32_t *)realloc(g.pcm, nc * sizeof(int32_t));
    if (!p) return FLAC__STREAM_DECODER_WRITE_STATUS_ABORT;
    g.pcm = p;
    g.cap = nc;
  }
  for (unsigned i = 0; i < f->header.blocksize; i++)
    for (unsigned ch = 0; ch < f->header.channels; ch++) g.pcm[g.len++] = buf[ch][i];
  return FLAC__STREAM_DECODER_WRITE_STATUS_CONTINUE;
}

static void md(const FLAC__StreamDecoder *d, const FLAC__StreamMetadata *m, void *c) {
  (void)d; (void)c;
  if (m->type != FLAC__METADATA_TYPE_STREAMINFO) return;
  const FLAC__StreamMetadata_StreamInfo *s = &m->data.stream_info;
  g.rate = s->sample_rate; g.ch = s->channels; g.bps = s->bits_per_sample; g.total = s->total_samples;
  static const uint8_t z[16] = {0};
  memcpy(g.md5, s->md5sum, 16);
  g.has_md5 = memcmp(z, s->md5sum, 16) != 0;
}

static void er(const FLAC__StreamDecoder *d, FLAC__StreamDecoderErrorStatus s, void *c) {
  (void)d; (void)s; (void)c;
  g.err = 1;
}

int fd_decode(const uint8_t *in, size_t n) {
  free(g.pcm);
  memset(&g, 0, sizeof g);
  g.in = in; g.n = n;
  FLAC__StreamDecoder *d = FLAC__stream_decoder_new();
  if (!d) return 3;
  FLAC__stream_decoder_set_md5_checking(d, 1);
  if (FLAC__stream_decoder_init_stream(d, rd, 0, 0, 0, 0, wr, md, er, 0) != FLAC__STREAM_DECODER_INIT_STATUS_OK) {
    FLAC__stream_decoder_delete(d);
    return 3;
  }
  FLAC__bool ok = FLAC__stream_decoder_process_until_end_of_stream(d);
  FLAC__StreamDecoderState st = FLAC__stream_decoder_get_state(d);
  /* finish() は MD5 不一致のとき false を返す (md5 未設定の stream は true) */
  FLAC__bool md5ok = FLAC__stream_decoder_finish(d);
  FLAC__stream_decoder_delete(d);
  if (!ok || g.err || st == FLAC__STREAM_DECODER_ABORTED) return 1;
  if (!md5ok) return 2;
  if (g.ch == 0 || g.bps == 0) return 3;
  return 0;
}

int32_t *fd_pcm(void) { return g.pcm; }
size_t fd_pcm_samples(void) { return g.len; }
uint32_t fd_rate(void) { return g.rate; }
uint32_t fd_channels(void) { return g.ch; }
uint32_t fd_bps(void) { return g.bps; }
uint32_t fd_total_lo(void) { return (uint32_t)g.total; }
uint32_t fd_total_hi(void) { return (uint32_t)(g.total >> 32); }
int fd_has_md5(void) { return g.has_md5; }
const uint8_t *fd_md5(void) { return g.md5; }
