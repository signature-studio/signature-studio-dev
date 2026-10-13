/* flds.h — DirectSound 互換の最小 C API (FL が実際に呼ぶ面のみ)。同じ SAB リング/worklet を使う。
 * 実測根拠: tools/audio/results/ds_static.txt (fl_ds_surface.py が FLEngine_x64.dll から受け手を解決して抽出)。
 *   IDirectSound            : SetCooperativeLevel(PRIORITY), CreateSoundBuffer (primary + secondary 各 1)
 *   primary IDirectSoundBuffer   : SetFormat, GetFormat
 *   secondary IDirectSoundBuffer : Lock, Unlock, GetCurrentPosition (play のみ / write のみの 2 呼出。もう一方は NULL), SetCurrentPosition, Play(LOOPING), Stop, QueryInterface(IDirectSoundNotify)
 *   IDirectSoundNotify      : SetNotificationPositions (2 点)
 * FL は SetVolume/SetFrequency を DS オブジェクトに呼ばない (INVENTORY §2 の当該集計は Delphi オブジェクトへの呼出を含んでいた) ので実装しない。
 *
 * 設計 (docs/PROTOCOL.md §8): secondary は shim 内の循環バイト列 (16bit PCM / float32 interleaved)。pump スレッドが
 * play cursor より T フレーム先まで planar f32 へ変換して ring に積む (= 「ring が DS の循環バッファ」の実体)。
 * play cursor = ring の消費フレーム (out_read) から導出、write cursor = pump が変換済みの位置 (そこまでは凍結)。
 * HRESULT / 定数は Win32 値をそのまま使用。COM vtable アダプタ (win64 ABI) は別 shim 行。 */
#ifndef FLDS_H
#define FLDS_H
#include <stdint.h>

typedef int32_t FLDSHR;
#define FLDS_OK                      0
#define FLDSERR_ALLOCATED            ((FLDSHR)0x8878000A)
#define FLDSERR_INVALIDPARAM         ((FLDSHR)0x80070057)
#define FLDSERR_INVALIDCALL          ((FLDSHR)0x88780032)
#define FLDSERR_GENERIC              ((FLDSHR)0x80004005)
#define FLDSERR_PRIOLEVELNEEDED      ((FLDSHR)0x88780046)
#define FLDSERR_OUTOFMEMORY          ((FLDSHR)0x8007000E)
#define FLDSERR_BADFORMAT            ((FLDSHR)0x88780064)
#define FLDSERR_NODRIVER             ((FLDSHR)0x88780078)
#define FLDSERR_UNINITIALIZED        ((FLDSHR)0x887800AA)

#define FLDSSCL_NORMAL    1u
#define FLDSSCL_PRIORITY  2u
#define FLDSSCL_EXCLUSIVE 3u   /* fail-fast (ブラウザに排他経路なし) */
#define FLDSSCL_WRITEPRIMARY 4u /* fail-fast */

#define FLDSBCAPS_PRIMARYBUFFER      0x00000001u
#define FLDSBCAPS_STATIC             0x00000002u
#define FLDSBCAPS_LOCHARDWARE        0x00000004u   /* ハードウェアボイス無し → FLDSERR_ALLOCATED */
#define FLDSBCAPS_LOCSOFTWARE        0x00000008u
#define FLDSBCAPS_CTRLPOSITIONNOTIFY 0x00000100u
#define FLDSBCAPS_STICKYFOCUS        0x00004000u
#define FLDSBCAPS_GLOBALFOCUS        0x00008000u
#define FLDSBCAPS_GETCURRENTPOSITION2 0x00010000u

#define FLDSBPLAY_LOOPING   1u
#define FLDSBLOCK_FROMWRITECURSOR 1u
#define FLDSBLOCK_ENTIREBUFFER    2u
#define FLDSBSTATUS_PLAYING 1u
#define FLDSBSTATUS_LOOPING 4u

#define FLDS_WAVE_FORMAT_PCM        1u
#define FLDS_WAVE_FORMAT_IEEE_FLOAT 3u
#define FLDS_WAVE_FORMAT_EXTENSIBLE 0xFFFEu

/* WAVEFORMATEXTENSIBLE のバイト互換 (FL の組立関数 0x674e10 (PCM) / 0x674e50 (EXTENSIBLE) の出力レイアウトそのまま) */
#pragma pack(push, 1)
typedef struct {
    uint16_t wFormatTag, nChannels;
    uint32_t nSamplesPerSec, nAvgBytesPerSec;
    uint16_t nBlockAlign, wBitsPerSample, cbSize;
    uint16_t wValidBitsPerSample;
    uint32_t dwChannelMask;
    uint8_t  SubFormat[16];
} flds_wfx_t;
#pragma pack(pop)

typedef struct { uint32_t dwSize, dwFlags, dwBufferBytes, dwReserved; const flds_wfx_t *lpwfxFormat; } flds_bufdesc_t;
typedef struct { uint32_t offset, event; } flds_notify_pos_t;   /* event は呼出側の識別子 (flds_wait_notify の mask は配列 index) */

typedef struct {
    uint32_t pump_frames, depth, T, ring_frames;   /* pump ブロック / 実効 depth / 目標充填 / ring */
    uint32_t underruns, silence_frames, quanta, latency_changes;
    uint64_t bytes_unlocked;
} flds_stats_t;

/* 設定 (secondary 作成前): pump ブロック (128 の倍数) と ring depth。既定 256 / 2 */
void   flds_configure(uint32_t pump_frames, uint32_t depth);

FLDSHR flds_create(void);                                  /* DirectSoundCreate */
FLDSHR flds_set_cooperative_level(uint32_t level);
FLDSHR flds_create_sound_buffer(const flds_bufdesc_t *desc);   /* primary / secondary (secondary で ring を開く) */
FLDSHR flds_primary_set_format(const flds_wfx_t *wfx);
FLDSHR flds_primary_get_format(flds_wfx_t *out);

FLDSHR flds_buf_lock(uint32_t offset, uint32_t bytes, void **p1, uint32_t *n1, void **p2, uint32_t *n2, uint32_t flags);
FLDSHR flds_buf_unlock(void *p1, uint32_t n1, void *p2, uint32_t n2);
FLDSHR flds_buf_get_current_position(uint32_t *play, uint32_t *write);   /* どちらも NULL 可 (FL は write=NULL) */
FLDSHR flds_buf_set_current_position(uint32_t pos);                      /* 停止中のみ (再生中は FLDSERR_INVALIDCALL) */
FLDSHR flds_buf_get_status(uint32_t *status);
FLDSHR flds_buf_play(uint32_t reserved, uint32_t priority, uint32_t flags);
FLDSHR flds_buf_stop(void);

/* IDirectSoundNotify: 位置を play cursor が「通過」(絶対位置が offset に到達) する度に mask の bit i が立つ。開始位置自身は通過に数えない */
FLDSHR flds_notify_set_positions(uint32_t n, const flds_notify_pos_t *pos);
int    flds_wait_notify(uint32_t timeout_ms, uint32_t *mask);   /* 0=発火 / 1=timeout / -1=停止中 */

void   flds_get_stats(flds_stats_t *s);
FLDSHR flds_release_buffer(void);   /* secondary を解放 (ring を閉じる) */
FLDSHR flds_release(void);          /* 全解放 */
#endif
