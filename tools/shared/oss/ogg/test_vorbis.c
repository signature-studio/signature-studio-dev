/* libogg 1.3.2 + libvorbis 1.3.5 検証ハーネス (FL oggio_x64 が内蔵する Xiph スタックと同一 version)。
   合成 PCM -> Vorbis VBR エンコード (Ogg ページをメモリへ) -> ogg_sync + vorbis_synthesis でデコード。
   native / wasm で ogg バイト列と復号 PCM のハッシュが完全一致することを確認する。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#include <ogg/ogg.h>
#include <vorbis/codec.h>
#include <vorbis/vorbisenc.h>

static uint64_t fnv(const void *p, size_t n, uint64_t h) {
  const unsigned char *c = p;
  for (size_t i = 0; i < n; i++) { h ^= c[i]; h *= 1099511628211ULL; }
  return h;
}
static unsigned char *out; static size_t outn, outcap;
static void put(const void *p, long n) {
  if (outn + n > outcap) { outcap = (outn + n) * 2; out = realloc(out, outcap); }
  memcpy(out + outn, p, n); outn += n;
}
static void flush_pages(ogg_stream_state *os, int force) {
  ogg_page og;
  while ((force ? ogg_stream_flush(os, &og) : ogg_stream_pageout(os, &og))) { put(og.header, og.header_len); put(og.body, og.body_len); }
}

int main(int argc, char **argv) {
  const int rate = 44100, ch = 2, N = rate * 2;
  int decode_only = argc > 1 && strcmp(argv[1], "-d") == 0;
  float *pcm[2]; pcm[0] = malloc(N * 4); pcm[1] = malloc(N * 4);
  /* libm 非依存の入力: 2 極共振器 y[n]=2cos(w)y[n-1]-y[n-2] (係数は double リテラル) + LCG ノイズ */
  const double c440 = 2 * 0.99616461394, c3000 = 2 * 0.65006463946, c660 = 2 * 0.99137137266; /* 2cos(2pi f/44100) 近似値 */
  double a1 = 0, a0 = 0.4 * 0.0624, b1 = 0, b0 = 0.2 * 0.4, d1 = 0, d0 = 0.4 * 0.0935; uint32_t s = 12345;
  for (int i = 0; i < N; i++) {
    s = s * 1664525u + 1013904223u;
    float noise = ((int)(s >> 8) / 8388608.0f - 1.0f) * 0.05f;
    double an = c440 * a0 - a1; a1 = a0; a0 = an;
    double bn = c3000 * b0 - b1; b1 = b0; b0 = bn;
    double dn = c660 * d0 - d1; d1 = d0; d0 = dn;
    pcm[0][i] = (float)(a0 + 0.5 * b0) + noise;
    pcm[1][i] = (float)d0 + noise;
  }
  ogg_packet op;
  if (!decode_only) {
  vorbis_info vi; vorbis_comment vc; vorbis_dsp_state vd; vorbis_block vb;
  ogg_stream_state os; ogg_packet h1, h2, h3;
  vorbis_info_init(&vi);
  if (vorbis_encode_init_vbr(&vi, ch, rate, 0.4f)) { puts("enc init fail"); return 1; }
  vorbis_comment_init(&vc);
  vorbis_analysis_init(&vd, &vi); vorbis_block_init(&vd, &vb);
  ogg_stream_init(&os, 4242);
  vorbis_analysis_headerout(&vd, &vc, &h1, &h2, &h3);
  ogg_stream_packetin(&os, &h1); ogg_stream_packetin(&os, &h2); ogg_stream_packetin(&os, &h3);
  flush_pages(&os, 1);
  for (int pos = 0; pos <= N;) {
    int n = pos == N ? 0 : (N - pos > 1024 ? 1024 : N - pos);
    if (n) { float **b = vorbis_analysis_buffer(&vd, n); memcpy(b[0], pcm[0] + pos, n * 4); memcpy(b[1], pcm[1] + pos, n * 4); }
    vorbis_analysis_wrote(&vd, n); pos += n ? n : 1;
    while (vorbis_analysis_blockout(&vd, &vb) == 1) {
      vorbis_analysis(&vb, NULL); vorbis_bitrate_addblock(&vb);
      while (vorbis_bitrate_flushpacket(&vd, &op)) { ogg_stream_packetin(&os, &op); flush_pages(&os, 0); }
    }
    if (!n) break;
  }
  flush_pages(&os, 1);
  printf("vendor=%s\nogg_bytes=%zu ogg_hash=%016llx\n", vc.vendor, outn, (unsigned long long)fnv(out, outn, 14695981039346656037ULL));
  ogg_stream_clear(&os); vorbis_block_clear(&vb); vorbis_dsp_clear(&vd); vorbis_comment_clear(&vc); vorbis_info_clear(&vi);

  if (argc > 1) { FILE *f = fopen(argv[1], "wb"); fwrite(out, 1, outn, f); fclose(f); }
  } else {
    FILE *f = fopen(argv[2], "rb"); fseek(f, 0, SEEK_END); outn = ftell(f); fseek(f, 0, SEEK_SET); out = malloc(outn); fread(out, 1, outn, f); fclose(f);
    printf("input_ogg_bytes=%zu ogg_hash=%016llx\n", outn, (unsigned long long)fnv(out, outn, 14695981039346656037ULL));
  }

  /* decode */
  ogg_sync_state oy; ogg_page og; ogg_stream_state dos; vorbis_info dvi; vorbis_comment dvc; vorbis_dsp_state dvd; vorbis_block dvb;
  ogg_sync_init(&oy);
  char *buf = ogg_sync_buffer(&oy, outn); memcpy(buf, out, outn); ogg_sync_wrote(&oy, outn);
  vorbis_info_init(&dvi); vorbis_comment_init(&dvc);
  int hdr = 0, inited = 0; uint64_t ph = 14695981039346656037ULL; long total = 0; int16_t maxv = 0;
  while (ogg_sync_pageout(&oy, &og) == 1) {
    if (!inited) { ogg_stream_init(&dos, ogg_page_serialno(&og)); inited = 1; }
    ogg_stream_pagein(&dos, &og);
    while (ogg_stream_packetout(&dos, &op) == 1) {
      if (hdr < 3) { if (vorbis_synthesis_headerin(&dvi, &dvc, &op) < 0) { puts("hdr fail"); return 1; } if (++hdr == 3) { vorbis_synthesis_init(&dvd, &dvi); vorbis_block_init(&dvd, &dvb); } continue; }
      if (vorbis_synthesis(&dvb, &op) == 0) vorbis_synthesis_blockin(&dvd, &dvb);
      float **pp; int sm;
      while ((sm = vorbis_synthesis_pcmout(&dvd, &pp)) > 0) {
        for (int i = 0; i < sm; i++) for (int c = 0; c < dvi.channels; c++) {
          int v = (int)floorf(pp[c][i] * 32767.f + .5f); if (v > 32767) v = 32767; if (v < -32768) v = -32768;
          int16_t x = (int16_t)v; ph = fnv(&x, 2, ph); if (x > maxv) maxv = x;
        }
        total += sm; vorbis_synthesis_read(&dvd, sm);
      }
    }
  }
  printf("decoded_frames=%ld ch=%ld rate=%ld pcm_hash=%016llx max=%d\n", total, dvi.channels, dvi.rate, (unsigned long long)ph, maxv);
  return 0;
}
