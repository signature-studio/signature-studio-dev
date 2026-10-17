/* flasio.h — ASIO 互換 (IASIO 実測 19 メソッド) の C API。FL 側の vtable 呼出を flasio_* に写像する。
 * 実測根拠: tools/audio/INVENTORY.md §2 (FLEngine の ASIO ラッパ 0xc53da0..0xc53ff0 が呼ぶメソッド集合)。
 * 型は Steinberg ASIO SDK 準拠 (long=32bit)。ILWASAPI2ASIO_x64 実測の報告値を既定とする。
 *
 * 注意: COM vtable アダプタ (win64 ABI の this/rcx, 64bit ポインタ構造体 ASIOCallbacks の変換) は
 * リフタの呼出規約が決まった後に生成する (docs/PROTOCOL.md §9 未実装一覧)。 */
#ifndef FLASIO_H
#define FLASIO_H
#include <stdint.h>

typedef int32_t  ASIOError;
typedef int32_t  ASIOBool;
typedef int32_t  ASIOLong;
enum {
    ASE_OK = 0, ASE_SUCCESS = 0x3f4847a0,
    ASE_NotPresent = -1000, ASE_HWMalfunction = -999, ASE_InvalidParameter = -998,
    ASE_InvalidMode = -997, ASE_SPNotAdvancing = -996, ASE_NoClock = -995, ASE_NoMemory = -994
};
enum { ASIOSTFloat32LSB = 19 }; /* ILWASAPI getChannelInfo 実測: type = 0x13 */
enum { kAsioSelectorSupported = 1, kAsioEngineVersion = 2, kAsioResetRequest = 3, kAsioBufferSizeChange = 4,
       kAsioResyncRequest = 5, kAsioLatenciesChanged = 6, kAsioSupportsTimeInfo = 7 };

typedef struct { uint32_t hi, lo; } ASIOSamples;   /* ASIOTimeStamp も同形 (ns) */
/* ASIOTime (Steinberg, pack(4)): FL の bufferSwitch ラッパは 0x94=148 バイトを確保している (実測) */
#pragma pack(push, 4)
typedef struct { double speed; ASIOSamples systemTime; ASIOSamples samplePosition; double sampleRate; uint32_t flags; char reserved[12]; } ASIOTimeInfo;
typedef struct { double speed; ASIOSamples timeCodeSamples; uint32_t flags; char future[64]; } ASIOTimeCode;
typedef struct { int32_t reserved[4]; ASIOTimeInfo timeInfo; ASIOTimeCode timeCode; } ASIOTime;
#pragma pack(pop)
enum { kSystemTimeValid = 1, kSamplePositionValid = 2, kSampleRateValid = 4 };
typedef struct { ASIOLong isInput, channelNum; void *buffers[2]; } ASIOBufferInfo;
typedef struct { ASIOLong channel; ASIOBool isInput, isActive; ASIOLong channelGroup, type; char name[32]; } ASIOChannelInfo;
typedef struct { ASIOLong index, associatedChannel, associatedGroup; ASIOBool isCurrentSource; char name[32]; } ASIOClockSource;
typedef struct {
    void (*bufferSwitch)(ASIOLong doubleBufferIndex, ASIOBool directProcess);
    void (*sampleRateDidChange)(double sRate);
    ASIOLong (*asioMessage)(ASIOLong selector, ASIOLong value, void *message, double *opt);
    ASIOTime *(*bufferSwitchTimeInfo)(ASIOTime *params, ASIOLong doubleBufferIndex, ASIOBool directProcess);
} ASIOCallbacks;

/* getBufferSize の報告値 (AU-7 #193 で既定を ILWASAPI に確定)。FLEngine は getBufferSize の min/max/granularity を読まず
 * (0xc58970 は出力先を自フレームに取り捨て、pref だけを大域へ保存して createBuffers に渡す; REPORT §11)、報告値は FL の挙動を変えない。
 * 既定 = ILWASAPI2ASIO_x64 実測値 (min256/max4096/pref512/gran0)。FLASIO_PROFILE_ILWASAPI=0 で shim 単体用の min=128/gran=128。
 * createBuffers はどちらの profile でも 128 の倍数 [128,4096] を受理する (B=128 e2e のため。profile は報告値だけを変える)。 */
#ifndef FLASIO_PROFILE_ILWASAPI
#define FLASIO_PROFILE_ILWASAPI 1
#endif

/* bufferSwitchTimeInfo / getSamplePosition の systemTime の意味 (AU-7 #193)。
 * 既定 = ILWASAPI2ASIO と同じ「コールバック時刻」: (uint32)timeGetTime() ms × 1e6 ns (FLEngine は systemTime だけを読み ms に変換して
 *        timeGetTime() と同じ時間軸で扱う; samplePosition/sampleRate は読まない)。shimx の timeGetTime は emscripten_get_now() なので同一基準。
 * FLASIO_SYSTIME_AUDIBLE=1 = 従来の「デバイス位置が聴こえる時刻 (outputLatency 込み)」。 */
#ifndef FLASIO_SYSTIME_AUDIBLE
#define FLASIO_SYSTIME_AUDIBLE 0
#endif

ASIOBool  flasio_init(void *sysHandle);
void      flasio_get_driver_name(char name[32]);
ASIOLong  flasio_get_driver_version(void);
ASIOError flasio_get_channels(ASIOLong *numIn, ASIOLong *numOut);
ASIOError flasio_get_latencies(ASIOLong *inLatency, ASIOLong *outLatency);
ASIOError flasio_get_buffer_size(ASIOLong *minS, ASIOLong *maxS, ASIOLong *prefS, ASIOLong *gran);
ASIOError flasio_can_sample_rate(double rate);
ASIOError flasio_get_sample_rate(double *rate);
ASIOError flasio_set_sample_rate(double rate);
ASIOError flasio_get_clock_sources(ASIOClockSource *clocks, ASIOLong *num);
ASIOError flasio_set_clock_source(ASIOLong reference);
ASIOError flasio_get_sample_position(ASIOSamples *sPos, ASIOSamples *tStamp);
ASIOError flasio_get_channel_info(ASIOChannelInfo *info);
ASIOError flasio_create_buffers(ASIOBufferInfo *infos, ASIOLong numChannels, ASIOLong bufferSize, ASIOCallbacks *cb);
ASIOError flasio_dispose_buffers(void);
ASIOError flasio_start(void);
ASIOError flasio_stop(void);
ASIOError flasio_output_ready(void);
ASIOError flasio_control_panel(void);
ASIOError flasio_future(ASIOLong selector, void *opt);

/* shim 固有: 統計/設定 (テスト用) */
typedef struct {
    uint32_t cb_count, cb_late, cb_max_us, cb_avg_us, underruns, silence_frames, in_overruns, in_underflows;
    uint32_t min_fill, avg_fill, wake_count, wait_timeouts, buffer_frames, depth, ring_frames, quanta;
    uint32_t reset_requests;
    uint32_t wake_hist[6];
    uint32_t latency_changes, T, burst_obs, timeinfo_cb;
    uint32_t grows, shrinks, T_max, T0;   /* T の拡張回数 / 減衰回数 / セッション内最大 T / 開始 T の下限 (frames) */
    uint32_t burst_hist[32];              /* バースト長ヒストグラム (512 f 刻み, flaudio.h burst_hist) */
    uint32_t seg_max_us[4];               /* do_buffer 区間の最大 µs: [0] in_read [1] memset [2] bufferSwitch 本体 (cb_max_us と同区間) [3] out_write */
} flasio_stats_t;
void flasio_get_stats(flasio_stats_t *s);
/* 診断用 (判定に使わない): producer 周期の時系列。行 7 double = [notify_ms(worklet Date.now), fill, underruns, wake, cb0, cb1, wr] (epoch ms) */
double *flasio_tl_ptr(void);
uint32_t flasio_tl_count(void);
void flasio_configure(uint32_t depth, uint32_t latency_hint);   /* create_buffers 前のみ */
#endif
