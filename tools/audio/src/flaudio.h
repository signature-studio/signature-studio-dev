/* flaudio.h — FL audio shim 共通: SAB リングバッファ + コントロールブロック + コマンドメールボックス。
 *
 * 設計: tools/audio/docs/PROTOCOL.md。JS 側ミラー: src/runtime/audio-layout.ts
 * (オフセットは flaudio.c の fla_layout_offsets() で実行時に自己検証する = 不一致なら fail-fast)。
 *
 * 全フィールドは wasm 共有メモリ上 (SharedArrayBuffer) に置く。AudioWorklet (JS) と
 * wasm pthread (C) が同一メモリを Atomics / __atomic_* で共有する。
 * フレームカウンタは 32bit 単調増加 (modular, 差が 2^31 未満の前提)。dev_frames のみ 64bit。
 */
#ifndef FLAUDIO_H
#define FLAUDIO_H

#include <stdint.h>
#include <stddef.h>

#define FLA_MAGIC      0x464c4131u /* 'FLA1' */
#define FLA_ABI        1u
#define FLA_QUANTUM    128u        /* AudioWorklet render quantum (固定) */
#define FLA_MAX_CH     8u          /* コンパイル時上限 (FL ILWASAPI 実測は 2in/2out) */
#define FLA_MAX_RING   (1u << 15)  /* ring_frames 上限 (2 の冪) */
#define FLA_PW_N       256u        /* producer の write 記録リングの件数 (fla_ctl_t.pw_trace) */
/* 目標充填 T の安全係数 (%): T の下限 = burst × FLA_BURST_PCT/100 + 2B。OPEN 較正 (flaudio.c) と実行中の拡張 (flasio.c) で共用。
 * 既定 125 は AU-24 (#2541) の実測で維持 (130/150 は grows と遅延を増やし、grows 0 にならなかった)。 */
#ifndef FLA_BURST_PCT
#define FLA_BURST_PCT 125u
#endif

/* ctl.state */
enum { FLA_ST_CLOSED = 0, FLA_ST_OPENED = 1, FLA_ST_RUNNING = 2 };
/* ctl.wl_state (worklet 側状態) */
enum { FLA_WL_IDLE = 0, FLA_WL_BUFFERING = 1, FLA_WL_PLAYING = 2 };
/* ctl.dev_events */
enum { FLA_EV_SUSPENDED = 1u << 0, FLA_EV_CLOSED = 1u << 1, FLA_EV_RATE_CHANGED = 1u << 2, FLA_EV_RESUMED = 1u << 3,
       FLA_EV_INPUT_CHANGED = 1u << 4 /* 入力デバイスの喪失/切替 (ASIO kAsioResetRequest の元) */ };
/* ctl.flags */
enum { FLA_F_DECLICK = 1u << 0, FLA_F_INPUT = 1u << 1 };

/* コマンド (wasm → main thread JS)。FLEngine 側は AudioContext/MIDI/getUserMedia に触れられない
 * (worker に AudioContext は無い) ため、制御面は全て main thread に委譲する。 */
enum {
    FLA_CMD_NONE = 0,
    FLA_CMD_OPEN = 1,       /* a0=sample_rate a1=out_ch a2=in_ch a3=latency_hint(0 interactive,1 balanced,2 playback,3 min)
                             * main: AudioContext 生成 + worklet module ロード。ack_res[0]=burst_frames(=ceil(baseLatency*sr), ブラウザの
                             * 音声コールバック粒度), [1]=実 sample_rate, [2]=outputLatency µs */
    FLA_CMD_CLOSE = 2,
    FLA_CMD_RESUME = 3,     /* AudioContext.resume() (suspend 復帰) */
    FLA_CMD_SET_SR = 4,     /* a0=new sample_rate: AudioContext 再生成 */
    FLA_CMD_MIDI_LIST = 5,  /* 設計のみ (docs) — 未実装 */
    FLA_CMD_INPUT_OPEN = 6, /* 未使用 (予約): 入力は ATTACH 時に FlAudioShimOptions.input (FlAudioInput) が接続する。実装すると fail-fast -2 */
    FLA_CMD_ATTACH = 7,     /* ring 確保後: AudioWorkletNode 生成 (processorOptions に最新 SAB/ctl/layout) + connect + resume */
    FLA_CMD_CONTROL_PANEL = 8 /* ASIO::controlPanel: main が FlAudioShimOptions.controlPanel (入力デバイス選択 UI 等) を開く。
                             * ack_status 0=UI を開いた, FLA_E_NO_PANEL=UI 未登録 */
};

/* 64 バイト境界で 6 ライン。オフセットは固定 (offsetof で JS 側と照合)。 */
typedef struct fla_ctl {
    /* ---- line0 @0: 構成 (wasm が open 時に書く, 他は read) ---- */
    uint32_t magic;            /* 0   */
    uint32_t abi;              /* 4   */
    uint32_t state;            /* 8   FLA_ST_* */
    uint32_t quantum;          /* 12  */
    uint32_t sample_rate;      /* 16  */
    uint32_t out_ch;           /* 20  */
    uint32_t in_ch;            /* 24  */
    uint32_t ring_frames;      /* 28  2 の冪 */
    uint32_t ring_mask;        /* 32  */
    uint32_t buffer_frames;    /* 36  ASIO bufferSize / WASAPI period */
    uint32_t depth;            /* 40  ring 目標充填 = depth * buffer_frames */
    uint32_t rebuffer_frames;  /* 44  underrun 後の再開閾値 */
    uint32_t out_ring_ptr;     /* 48  wasm リニアメモリ内バイトオフセット (planar f32, ch*ring_frames) */
    uint32_t in_ring_ptr;      /* 52  */
    uint32_t flags;            /* 56  */
    uint32_t dev_events;       /* 60  main→wasm イベントビット FLA_EV_* (wasm が atomic exchange で消費) */
    /* ---- line1 @64: worklet が書く ---- */
    uint64_t dev_frames;       /* 64  worklet が render した総フレーム (デバイスクロック master, 単調) */
    uint64_t dev_ctx_time_bits;/* 72  その時点の currentTime (f64 ビット) — clock_seq で一貫性確保 */
    uint32_t out_read;         /* 80  リング read idx (frames, modular) */
    uint32_t in_write;         /* 84  入力リング write idx */
    uint32_t underruns;        /* 88  underrun 発生 quantum 数 */
    uint32_t silence_frames;   /* 92  無音で埋めたフレーム数 */
    uint32_t quanta;           /* 96  process() 呼出数 */
    uint32_t in_overruns;      /* 100 入力リング溢れ (古い入力を破棄) */
    uint32_t wl_state;         /* 104 FLA_WL_* */
    uint32_t clock_seq;        /* 108 seqlock (奇数=更新中) */
    uint64_t play_start_frame; /* 112 現 gen 開始時の dev_frames (ASIO sample position 原点) */
    uint32_t clock_jumps;      /* 120 currentFrame が process() 呼出間で連続しなかった回数 (ブラウザ音声スレッドのスキップ) */
    uint32_t clock_jump_frames;/* 124 その合計フレーム数 */
    /* ---- line2 @128: producer (wasm) が書く ---- */
    uint32_t out_write;        /* 128 */
    uint32_t in_read;          /* 132 */
    uint32_t wake_target;      /* 136 producer が起こしてほしい out_read 値 */
    uint32_t gen;              /* 140 start 毎に ++ */
    uint32_t go;               /* 144 1=worklet は消費してよい */
    uint32_t in_wake_target;   /* 148 入力待ち用 (WASAPI capture / 入力 blocking read) */
    uint32_t tick_target;      /* 152 device クロック待ち: dev_frames(低32bit) がこれを超えたら worklet が quanta を notify */
    uint32_t notify_ms;        /* 156 worklet が producer を notify した時刻 (Date.now() 下位32bit, ms) — wake 遅延計測用 */
    uint32_t burst_obs;        /* 160 worklet が観測した最長バースト (連続 process() の総フレーム数)。baseLatency より実態に近い */
    uint32_t clock_skip_frames;/* 164 clock_jump_frames の正の成分 (process() 間に描画されなかったフレーム = 実スキップ) */
    uint32_t clock_dup_frames; /* 168 clock_jump_frames の負の成分の絶対値 (重複・後退) */
    uint32_t clock_jump_max;   /* 172 1 回の jump の最大 abs (frames), gen 開始で 0 */
    uint32_t clock_jump_max_q; /* 176 その最大 jump が起きた quantum 番号 (process() の通し番号) */
    uint32_t clock_first_q;    /* 180 最初の jump の quantum 番号 (bit31=1 は負 = 重複・後退)。gen 開始で 0 */
    uint32_t clock_last_q;     /* 184 直近の jump の quantum 番号 (bit31 は同上) */
    uint32_t cb_max_q;         /* 188 cb_max_us を更新した時点の quantum 番号 (process() 通し番号) */
    /* ---- line3 @192: main thread が書く 時刻対応 (getOutputTimestamp) ---- */
    uint64_t ref_ctx_time_bits;/* 192 contextTime(f64) */
    uint64_t ref_epoch_ms_bits;/* 200 performance.timeOrigin+performanceTime(f64) */
    uint32_t ref_seq;          /* 208 seqlock */
    uint32_t out_latency_us;   /* 212 AudioContext.outputLatency (µs) */
    uint32_t base_latency_us;  /* 216 AudioContext.baseLatency (µs) */
    uint32_t pad3[9];          /* 220 */
    /* ---- line4 @256: コマンドメールボックス (wasm → main, 同期 RPC) ---- */
    uint32_t cmd_seq;          /* 256 wasm が ++ して futex_wake */
    uint32_t cmd_op;           /* 260 */
    uint32_t cmd_arg[4];       /* 264 */
    uint32_t ack_seq;          /* 280 main が cmd_seq を写して futex notify */
    int32_t  ack_status;       /* 284 0=OK, 負=エラー */
    uint32_t ack_res[4];       /* 288 */
    uint32_t ctrl_ready;       /* 304 main thread controller 常駐フラグ */
    uint32_t pad4[3];          /* 308 */
    /* ---- line5 @320: producer 統計 ---- */
    uint32_t cb_count;         /* 320 bufferSwitch 呼出数 */
    uint32_t cb_late;          /* 324 deadline 超過 (fill < buffer_frames で起床) */
    uint32_t cb_max_us;        /* 328 コールバック最大所要 µs */
    uint32_t cb_sum_us_lo;     /* 332 */
    uint32_t wake_count;       /* 336 futex 起床回数 */
    uint32_t wait_timeouts;    /* 340 */
    uint32_t in_underflows;    /* 344 入力データ不足でゼロ補填した回数 */
    uint32_t min_fill;         /* 348 bufferSwitch 起床時 ring 充填 (frames) の最小値 */
    uint32_t fill_sum_lo;      /* 352 fill 合計 (平均用) */
    uint32_t fill_samples;     /* 356 */
    /* 360..383 */
    uint32_t wake_hist[6];     /* 360 wake 遅延ヒストグラム (ms): <1,<2,<4,<8,<16,>=16 (Date.now 分解能 ±1ms) */
    /* ---- line6 @384: producer の write 単位の記録 (FLA_PW_N 件のリング)。件 k = [w (write 開始 frame), fill (起床時の充填),
     * 起床時刻 µs, 完了時刻 µs] (performance.now の下 32bit)。pw_n は通算数 (添字 = pw_n % FLA_PW_N) ---- */
    uint32_t pw_n;             /* 384 */
    uint32_t pw_trace[FLA_PW_N * 4]; /* 388 */
} fla_ctl_t;

#define FLA_CTL_SIZE 4488u

/* ---- ABI 自己検証用: JS が同じ配列を持つ (audio-layout.ts) ---- */
typedef struct { const char *name; uint32_t off; } fla_layout_entry_t;
const fla_layout_entry_t *fla_layout_offsets(int *count);

/* ---- core API (flaudio.c) ---- */
fla_ctl_t *fla_ctl(void);                 /* 静的コントロールブロック (JS へは fla_ctl_ptr で公開) */
uintptr_t  fla_ctl_ptr(void);
/* 同期 RPC: メイン JS へコマンド送信し ack を待つ。timeout_ms 超過 → -1。pthread 内専用 (main browser thread では fail-fast) */
int  fla_cmd(uint32_t op, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t res[4], uint32_t timeout_ms);
/* ring 確保 + ctl 初期化。成功 0。失敗は負値 (abort しない):
 *   -1 = RPC 失敗/タイムアウト, FLA_E_BURST_TOO_LARGE = OPEN 較正 burst が大きすぎ ring に収まらない
 *   ((depth+2)*B > FLA_MAX_RING。depth は burst から自動算出し固定上限なし。AudioContext は閉じて CLOSED に戻す) */
#define FLA_E_BURST_TOO_LARGE (-100)
#define FLA_E_NO_PANEL (-3)   /* CONTROL_PANEL の ack_status: main に UI が登録されていない */
int  fla_open(uint32_t sr, uint32_t out_ch, uint32_t in_ch, uint32_t buffer_frames, uint32_t depth, uint32_t flags);
void fla_close(void);
/* テスト専用: OPEN 較正 burst の下限を強制 (0 = 無効)。ring 超過エラー経路を決定的に再現する */
void fla_test_set_burst_floor(uint32_t frames);
/* start: ring/idx リセット → (prefill は呼び出し側) → fla_go() */
void fla_reset_indexes(void);
void fla_go(void);
void fla_halt(void);                       /* go=0 → worklet が IDLE になるのを待つ */
/* producer API */
uint32_t fla_out_fill(void);               /* write - read (frames) */
/* fill (write-read) <= max_fill になるまでブロック (Atomics.wait / worklet が notify)。
 * 戻り: 0 OK, 1 timeout, -1 halted(state!=RUNNING) */
int  fla_out_wait_fill_le(uint32_t max_fill, uint32_t timeout_ms);
/* planar f32 の ch 別ポインタ列を frames フレームリングへコピー (wrap 対応) → write idx 公開 */
void fla_out_write(const float *const *planar, uint32_t frames);
void fla_out_write_silence(uint32_t frames);
/* 入力: 利用可能フレーム数, 読み出し (不足分はゼロ, in_underflows++) */
uint32_t fla_in_avail(void);
uint32_t fla_in_read(float *const *planar, uint32_t frames);
/* device クロック (dev_frames 低32bit) が target_lo に達するまでブロック。0=到達, 1=timeout, -1=closed */
int  fla_wait_dev_frames(uint32_t target_lo, uint32_t timeout_ms);
/* クロック: worklet が render した位置 + その audible 時刻 (epoch ns)。ref 未設定なら ns=0 */
typedef struct { uint64_t pos_frames; uint64_t audible_ns; uint64_t play_start; double ctx_time; } fla_clock_t;
void fla_clock_read(fla_clock_t *out);
double fla_now_ms(void);                   /* performance.timeOrigin + performance.now() (epoch ms) */
/* fail-fast */
void fla_failfast(const char *api, const char *why);

#endif
