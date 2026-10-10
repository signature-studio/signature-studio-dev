/* flwasapi.h — WASAPI (IAudioClient + IAudioRenderClient) 互換の最小 C API。
 * 実測: FLEngine は WASAPI を直接呼ばない (ILWASAPI2ASIO が IMMDeviceEnumerator→IAudioClient shared/float/
 * ポーリング + IAudioRenderClient を使用)。本 API は (a) ILWASAPI 相当ドライバを shim 内で再現する場合と
 * (b) 将来の第三者コード用の優先度 P2 の面。capture 側は設計のみ (fail-fast スタブ)。
 * HRESULT は Win32 値をそのまま使用。 */
#ifndef FLWASAPI_H
#define FLWASAPI_H
#include <stdint.h>

typedef int32_t FLHR;
#define FL_S_OK                        0
#define FL_AUDCLNT_E_NOT_INITIALIZED   ((FLHR)0x88890001)
#define FL_AUDCLNT_E_ALREADY_INITIALIZED ((FLHR)0x88890002)
#define FL_AUDCLNT_E_BUFFER_TOO_LARGE  ((FLHR)0x88890006)
#define FL_AUDCLNT_E_OUT_OF_ORDER      ((FLHR)0x88890007)
#define FL_AUDCLNT_E_UNSUPPORTED_FORMAT ((FLHR)0x88890008)
#define FL_AUDCLNT_E_INVALID_SIZE      ((FLHR)0x88890009)
#define FL_AUDCLNT_E_NOT_STOPPED       ((FLHR)0x88890005)
#define FL_AUDCLNT_E_EVENTHANDLE_NOT_SET ((FLHR)0x88890014)
#define FL_AUDCLNT_E_DEVICE_INVALIDATED ((FLHR)0x88890004)
#define FL_AUDCLNT_SHAREMODE_SHARED    0
#define FL_AUDCLNT_STREAMFLAGS_EVENTCALLBACK 0x00040000u
#define FL_AUDCLNT_BUFFERFLAGS_SILENT  2u
#define FL_WAIT_OBJECT_0 0
#define FL_WAIT_TIMEOUT  258

typedef struct { uint32_t sample_rate, channels; /* 常に IEEE_FLOAT 32bit */ } flwasapi_fmt_t;

FLHR flwasapi_get_mix_format(flwasapi_fmt_t *f);
FLHR flwasapi_get_device_period(int64_t *default_hns, int64_t *min_hns);
FLHR flwasapi_is_format_supported(const flwasapi_fmt_t *f);
FLHR flwasapi_initialize(int share_mode, uint32_t stream_flags, int64_t buffer_duration_hns, int64_t periodicity_hns, const flwasapi_fmt_t *f);
FLHR flwasapi_get_buffer_size(uint32_t *frames);
FLHR flwasapi_get_stream_latency(int64_t *hns);
FLHR flwasapi_get_current_padding(uint32_t *frames);
FLHR flwasapi_set_event_handle(int enable);              /* Win32 HANDLE の代わりに有効化フラグ。wait は flwasapi_wait_event */
int  flwasapi_wait_event(uint32_t timeout_ms);           /* FL_WAIT_OBJECT_0 / FL_WAIT_TIMEOUT (period 毎に 1 回, auto-reset 相当) */
FLHR flwasapi_start(void);
FLHR flwasapi_stop(void);
FLHR flwasapi_reset(void);
FLHR flwasapi_render_get_buffer(uint32_t frames, float **data);           /* interleaved f32 */
FLHR flwasapi_render_release_buffer(uint32_t frames, uint32_t flags);
FLHR flwasapi_release(void);
/* capture: 未実装 (docs/PROTOCOL.md §6 に設計)。呼ぶと fail-fast */
FLHR flwasapi_capture_get_buffer(float **data, uint32_t *frames, uint32_t *flags);
FLHR flwasapi_capture_release_buffer(uint32_t frames);
#endif
