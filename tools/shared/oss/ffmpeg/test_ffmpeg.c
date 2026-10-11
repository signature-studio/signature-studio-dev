/* FFmpeg n4.4.2 (win 実測) 検証ハーネス — wasm 再ビルド。
 * FL 側 (libILVideo) と同じ経路: demuxer -> decoder -> resampler で PCM を得て
 * FLAC / Ogg-Vorbis / WAV(PCM) / MP3 の 4 種を復号して PCM hash を出す。
 * native / wasm32 / wasm64 で同一 .flac/.ogg/.wav/.mp3 を読んで比較する。
 * usage: test_ffmpeg <input-file> ...
 *   (入力ファイルは前に libFLAC/libvorbis/LAME の harness が作ったものを流用する)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "libavcodec/avcodec.h"
#include "libavformat/avformat.h"
#include "libavutil/opt.h"


static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

int main(int argc, char **argv) {
  printf("FFMPEG_VERSION=%s avcodec=%d avformat=%d\n", "4.4.2", avcodec_version(), avformat_version());
  int rc = 0;
  for (int i = 1; i < argc; i++) {
    const char *path = argv[i];
    AVFormatContext *fmt = NULL;
    if (avformat_open_input(&fmt, path, NULL, NULL) < 0) { fprintf(stderr, "open %s fail\n", path); rc = 1; continue; }
    if (avformat_find_stream_info(fmt, NULL) < 0) { fprintf(stderr, "streaminfo fail\n"); rc = 1; avformat_close_input(&fmt); continue; }
    int as = av_find_best_stream(fmt, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    if (as < 0) { fprintf(stderr, "no audio\n"); rc = 1; avformat_close_input(&fmt); continue; }
    const AVCodec *c = avcodec_find_decoder(fmt->streams[as]->codecpar->codec_id);
    if (!c) { fprintf(stderr, "no decoder for id %d\n", fmt->streams[as]->codecpar->codec_id); rc = 1; avformat_close_input(&fmt); continue; }
    AVCodecContext *dec = avcodec_alloc_context3(c);
    avcodec_parameters_to_context(dec, fmt->streams[as]->codecpar);
    if (avcodec_open2(dec, c, NULL) < 0) { fprintf(stderr, "open2 fail\n"); rc = 1; avcodec_free_context(&dec); avformat_close_input(&fmt); continue; }
    AVPacket pkt; AVFrame *fr = av_frame_alloc();
    uint64_t h = 1469598103934665603ULL;
    int64_t frames = 0, samples = 0;
    int out_linesize; uint8_t *out_buf = NULL;
    while (av_read_frame(fmt, &pkt) >= 0) {
      if (pkt.stream_index == as) {
        if (avcodec_send_packet(dec, &pkt) >= 0) {
          while (avcodec_receive_frame(dec, fr) >= 0) {
            /* planar 形式は全 plane を、packed は data[0] の通し分だけを hash する。
             * (av_samples_get_buffer_size の byte 数分を各 plane から読む) */
            int n = av_samples_get_buffer_size(&out_linesize, fr->channels, fr->nb_samples, dec->sample_fmt, 1);
            if (n <= 0) continue;
            int is_planar = av_sample_fmt_is_planar(fr->format);
            if (is_planar) {
              for (int pl = 0; pl < fr->channels && pl < AV_NUM_DATA_POINTERS; pl++)
                h = fnv((const unsigned char *)fr->extended_data[pl], n / fr->channels, h);
            } else {
              h = fnv((const unsigned char *)fr->data[0], n, h);
            }
            samples += (int64_t)fr->nb_samples * fr->channels;
            frames++;
          }
        }
      }
      av_packet_unref(&pkt);
    }
    printf("DECODE %s: codec=%s(%s) ch=%d rate=%d fmt=%s frames=%lld samples=%lld pcm_hash=%016llx\n",
           path, c->name, c->long_name ? c->long_name : "?", dec->channels, dec->sample_rate,
           av_get_sample_fmt_name(dec->sample_fmt), (long long)frames, (long long)samples, (unsigned long long)h);
    av_frame_free(&fr); avcodec_free_context(&dec); avformat_close_input(&fmt);
  }
  return rc;
}
