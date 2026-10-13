/* flmidi.h — FL MIDI shim 転送層: SAB MIDI ring + コントロールブロック + mailbox RPC + デバイス表。
 *
 * 設計: tools/audio/docs/PROTOCOL.md §9。JS 側ミラー: src/runtime/midi-layout.ts (flm_layout_* で起動時に自己検証)。
 * 全て wasm 静的メモリ上 (= shared memory)。main thread (または Worker) の JS が Atomics で直接読み書きする。
 *
 * ring レコード = 16B ヘッダ + payload (16B 境界へ切上げ)。index は 32bit 単調増加 (byte 単位, modular)。
 *   w0 = slot(8) | kind(8) << 8 | gen(16) << 16
 *   w1 = SHORT: packed msg (status | d1<<8 | d2<<16) / SYSEX: バイト長 / STATE: FLM_ST_*
 *   f64 = ts (epoch ms = performance.timeOrigin + event.timeStamp)。出力 ring は 0 = 即時
 * 入力 ring: producer = JS, consumer = wasm の MIDI スレッド。溢れたら新しい方を捨てて in_dropped++ (リアルタイム入力は待てない)。
 * 出力 ring: producer = wasm (FL スレッド, 内部 mutex で直列化), consumer = JS → MIDIOutput.send。 */
#ifndef FLMIDI_H
#define FLMIDI_H
#include <stdint.h>
#include <stddef.h>

#define FLM_MAGIC          0x464c4d31u /* 'FLM1' */
#define FLM_ABI            1u
#define FLM_MAX_DEV        16u         /* 方向ごとのデバイス表上限 */
#define FLM_REC            16u
#define FLM_IN_RING_BYTES  (1u << 16)
#define FLM_OUT_RING_BYTES (1u << 16)
#define FLM_MAX_SYSEX      (FLM_IN_RING_BYTES - 2 * FLM_REC)
#define FLM_NAME_CHARS     32u         /* UTF-16 code unit (NUL 含む) = szPname[32] */
#define FLM_DEV_ENTRY      96u

enum { FLM_K_SHORT = 0, FLM_K_SYSEX = 1, FLM_K_STATE = 2 };
enum { FLM_ST_LOST = 1 };
enum { FLM_CMD_NONE = 0, FLM_CMD_SCAN = 1, FLM_CMD_OPEN_IN = 2, FLM_CMD_CLOSE_IN = 3, FLM_CMD_OPEN_OUT = 4, FLM_CMD_CLOSE_OUT = 5 };
/* ack_status: 0 OK / FLM_E_NODEV = 指定 key のデバイスが無い / FLM_E_OPEN = port.open() 失敗 / FLM_E_DENIED = 権限なし・Web MIDI 無し */
enum { FLM_E_DENIED = -4, FLM_E_OPEN = -3, FLM_E_NODEV = -2 };

typedef struct flm_ctl {
    /* ---- line0 @0: 構成 (wasm が書く) ---- */
    uint32_t magic;          /* 0  */
    uint32_t abi;            /* 4  */
    uint32_t state;          /* 8  1 = ring/表 初期化済み */
    uint32_t in_ring_ptr;    /* 12 */
    uint32_t in_ring_bytes;  /* 16 */
    uint32_t out_ring_ptr;   /* 20 */
    uint32_t out_ring_bytes; /* 24 */
    uint32_t dev_tbl_ptr;    /* 28 [2][FLM_MAX_DEV] × FLM_DEV_ENTRY, dir 0 = in / 1 = out */
    uint32_t max_dev;        /* 32 */
    uint32_t ctrl_ready;     /* 36 JS コントローラ常駐フラグ */
    uint32_t pad0[6];        /* 40 */
    /* ---- line1 @64: JS が書く ---- */
    uint32_t in_w;           /* 64 */
    uint32_t in_dropped;     /* 68 入力 ring 溢れで捨てた件数 */
    uint32_t in_accepted;    /* 72 ring に積んだ件数 */
    uint32_t main_errors;    /* 76 JS 側で不正 (長すぎ sysex・未対応メッセージ) として捨てた件数 */
    uint32_t out_r;          /* 80 */
    uint32_t out_errors;     /* 84 send 失敗・未知 slot */
    uint32_t out_sent;       /* 88 send した件数 */
    uint32_t pad1[9];        /* 92 */
    /* ---- line2 @128: wasm が書く ---- */
    uint32_t in_r;           /* 128 */
    uint32_t out_w;          /* 132 */
    uint32_t wake;           /* 136 MIDI スレッド起床用 futex。JS / wasm のどちらも ++ して notify */
    uint32_t out_full;       /* 140 出力 ring 満杯で MIDIERR_NOTREADY を返した回数 */
    uint32_t sx_nobuf;       /* 144 SysEx 受信時に空きバッファが無く捨てた件数 */
    uint32_t in_stale;       /* 148 閉じた/世代違いの slot 宛で捨てた件数 */
    uint32_t in_prestart;    /* 152 midiInStart 前・Stop 後・Start より古い ts で捨てた件数 */
    uint32_t cb_events;      /* 156 コールバック呼出回数 */
    uint32_t pad2[8];        /* 160 */
    /* ---- line3 @192: デバイス表 (JS が書く, tbl_seq seqlock) ---- */
    uint32_t tbl_seq;        /* 192 奇数 = 更新中 */
    uint32_t n_in;           /* 196 */
    uint32_t n_out;          /* 200 */
    uint32_t scan_gen;       /* 204 スキャンのたびに ++ */
    uint32_t pad3[12];       /* 208 */
    /* ---- line4 @256: mailbox (wasm → JS 同期 RPC) ---- */
    uint32_t cmd_seq;        /* 256 */
    uint32_t cmd_op;         /* 260 */
    uint32_t cmd_arg[4];     /* 264 */
    uint32_t ack_seq;        /* 280 */
    int32_t  ack_status;     /* 284 */
    uint32_t ack_res[4];     /* 288 */
    uint32_t pad4[4];        /* 304 */
} flm_ctl_t;
#define FLM_CTL_SIZE 320u

/* デバイス表エントリ (96B): name = UTF-16 (最大 31 文字 + NUL) */
typedef struct { uint16_t name[FLM_NAME_CHARS]; uint32_t mid_pid; uint32_t state; uint32_t key; uint8_t pad[20]; } flm_dev_t;
typedef struct { uint32_t slot, kind, gen, val; double ts; } flm_rec_t;

flm_ctl_t *flm_ctl(void);
void flm_init(void);                                  /* 冪等。ctl/ring/表を初期化 */
double flm_now_ms(void);                              /* performance.timeOrigin + performance.now() */
void flm_bump_wake(void);
int  flm_wait_wake(uint32_t seen, uint32_t timeout_ms); /* wake != seen なら即戻る */
int  flm_rpc(uint32_t op, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t res[4], uint32_t timeout_ms);
/* 入力 ring を 1 件取り出す (consumer 専用)。戻り 1 = 取得 / 0 = 空。payload は cap 以上の領域 */
int  flm_in_pop(flm_rec_t *r, uint8_t *payload, uint32_t cap);
/* 出力 ring へ積む (呼び側が排他)。0 = OK / -1 = 満杯。*end に積み後の out_w (完了判定用) */
int  flm_out_push(uint32_t slot, uint32_t gen, uint32_t kind, uint32_t val, const uint8_t *data, uint32_t len, uint32_t *end);
int  flm_dev_snapshot(flm_dev_t out[2][FLM_MAX_DEV], uint32_t n[2]); /* seqlock で一貫読み, 戻り = scan_gen */
void flm_failfast(const char *api, const char *why);

typedef struct { const char *name; uint32_t off; } flm_layout_entry_t;
int flm_layout_count(void);
uint32_t flm_layout_off(int i);
const char *flm_layout_name(int i);
uintptr_t flm_ctl_ptr(void);

/* ---- winmm 層 (flmidi_winmm.c) の管理 API ---- */
int      flmidi_rescan(void);                          /* SCAN RPC を即実行 (statechange を待たない)。0 = OK */
uint32_t flmidi_scan_gen(void);
void     flmidi_get_stats(uint32_t out[16]);
void     flmidi_test_pause(int on);                    /* テスト専用: MIDI スレッドの ring 消費を止める (溢れの決定的再現) */
#endif
