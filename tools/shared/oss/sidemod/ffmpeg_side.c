/* FFmpeg n4.4.2 side module の公開 ABI (LGL-4)。
 * 差し替え境界は ss_ff_* だけ。AV* 型はモジュール外へ出さない。 */
#include <stdint.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE __attribute__((visibility("default")))
#endif
#include "libavcodec/avcodec.h"
#include "libavformat/avformat.h"

#define SS_ABI 1

typedef struct {
  int channels, rate;
  long long frames, samples;
  unsigned long long pcm_hash;
  char codec[32];
} ss_ff_info;

static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

EMSCRIPTEN_KEEPALIVE int ss_abi_version(void) { return SS_ABI; }
EMSCRIPTEN_KEEPALIVE const char *ss_ff_license(void) { return avcodec_license(); }
EMSCRIPTEN_KEEPALIVE const char *ss_ff_configuration(void) { return avcodec_configuration(); }
EMSCRIPTEN_KEEPALIVE int ss_ff_struct_size(void) { return (int)sizeof(ss_ff_info); }

/* path を復号し、全 plane の PCM を FNV-1a した値と諸元を info に入れる。成功 0 */
EMSCRIPTEN_KEEPALIVE int ss_ff_decode(const char *path, ss_ff_info *info) {
  AVFormatContext *fmt = NULL;
  if (avformat_open_input(&fmt, path, NULL, NULL) < 0) return 1;
  if (avformat_find_stream_info(fmt, NULL) < 0) { avformat_close_input(&fmt); return 2; }
  int as = av_find_best_stream(fmt, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
  if (as < 0) { avformat_close_input(&fmt); return 3; }
  const AVCodec *c = avcodec_find_decoder(fmt->streams[as]->codecpar->codec_id);
  if (!c) { avformat_close_input(&fmt); return 4; }
  AVCodecContext *dec = avcodec_alloc_context3(c);
  avcodec_parameters_to_context(dec, fmt->streams[as]->codecpar);
  if (avcodec_open2(dec, c, NULL) < 0) { avcodec_free_context(&dec); avformat_close_input(&fmt); return 5; }
  AVPacket pkt; AVFrame *fr = av_frame_alloc();
  uint64_t h = 1469598103934665603ULL;
  long long frames = 0, samples = 0;
  int linesize;
  while (av_read_frame(fmt, &pkt) >= 0) {
    if (pkt.stream_index == as && avcodec_send_packet(dec, &pkt) >= 0) {
      while (avcodec_receive_frame(dec, fr) >= 0) {
        int n = av_samples_get_buffer_size(&linesize, fr->channels, fr->nb_samples, dec->sample_fmt, 1);
        if (n <= 0) continue;
        if (av_sample_fmt_is_planar(fr->format)) {
          for (int pl = 0; pl < fr->channels && pl < AV_NUM_DATA_POINTERS; pl++)
            h = fnv((const unsigned char *)fr->extended_data[pl], n / fr->channels, h);
        } else {
          h = fnv((const unsigned char *)fr->data[0], n, h);
        }
        samples += (long long)fr->nb_samples * fr->channels;
        frames++;
      }
    }
    av_packet_unref(&pkt);
  }
  info->channels = dec->channels; info->rate = dec->sample_rate;
  info->frames = frames; info->samples = samples; info->pcm_hash = h;
  int i = 0; for (; c->name[i] && i < 31; i++) info->codec[i] = c->name[i]; info->codec[i] = 0;
  av_frame_free(&fr); avcodec_free_context(&dec); avformat_close_input(&fmt);
  return 0;
}
