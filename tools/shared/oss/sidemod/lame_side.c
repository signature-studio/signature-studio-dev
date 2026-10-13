/* LAME 3.99.5 side module の公開 ABI (LGL-4)。
 * 差し替え境界はこの ss_lame_* だけ。lame.h の型はモジュール外へ出さない。
 * mpglib (GPL のデコード部) は含めない: configure --disable-decoder (HAVE_MPGLIB 未定義)。 */
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE __attribute__((visibility("default")))
#endif
#include "lame.h"

#define SS_ABI 1

EMSCRIPTEN_KEEPALIVE int ss_abi_version(void) { return SS_ABI; }
EMSCRIPTEN_KEEPALIVE const char *ss_lame_version(void) { return get_lame_version(); }

EMSCRIPTEN_KEEPALIVE void *ss_lame_open(int rate, int channels, int brate, int quality) {
  lame_global_flags *g = lame_init();
  if (!g) return 0;
  lame_set_num_channels(g, channels);
  lame_set_in_samplerate(g, rate);
  lame_set_out_samplerate(g, rate);
  lame_set_brate(g, brate);
  lame_set_mode(g, channels == 1 ? MONO : STEREO);
  lame_set_quality(g, quality);
  lame_set_VBR(g, vbr_default);
  lame_set_bWriteVbrTag(g, 1);
  if (lame_init_params(g) < 0) { lame_close(g); return 0; }
  return g;
}

EMSCRIPTEN_KEEPALIVE int ss_lame_encode(void *h, short *l, short *r, int n, unsigned char *out, int cap) {
  return lame_encode_buffer((lame_global_flags *)h, l, r, n, out, cap);
}

EMSCRIPTEN_KEEPALIVE int ss_lame_flush(void *h, unsigned char *out, int cap) {
  return lame_encode_flush((lame_global_flags *)h, out, cap);
}

EMSCRIPTEN_KEEPALIVE void ss_lame_close(void *h) { lame_close((lame_global_flags *)h); }
