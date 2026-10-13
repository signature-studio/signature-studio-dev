/* flapi provider の C ABI (BRIDGE.md §2/§5)。
 *   int fl_api_call(int fn_id, const fl_slot *argv, int argc, fl_slot *ret);
 * fn_id = analysis/flapi/flapi_ids.json の列挙順 (Python fl_api.install / JS 共通)。
 * 戻り値 0 = 呼出し成立 (FL 側エラーは ret.tag='E' + code 1..8)、非 0 = 転送失敗 (不明 fn_id / 不正 tag)。
 * 文字列スロットは UTF-8 で、末尾に NUL を置く (len は NUL を含まない)。
 * ret の S/J/E 本体は malloc 済みで、所有権は呼出し側 (flpy.c) に移る (読んだ後 free する)。
 */
#ifndef FL_API_H
#define FL_API_H
#include <stdint.h>
#include <stddef.h>

/* 16B スロット: tag@0 code@4 payload@8 (flhost_lib.js / flpy.c と同一レイアウト) */
typedef struct {
    uint8_t tag; /* N B I D S Y F (引数) / N B I D S Y J E (戻り) */
    uint8_t _pad[3];
    int32_t code; /* 'E' のとき FL エラー code */
    union {
        int64_t i; /* B / I / F(callback id) */
        double d;  /* D */
        struct { uint32_t ptr, len; } s; /* S Y J E(msg) : wasm 線形メモリ上 */
    } v;
} fl_slot;

_Static_assert(sizeof(fl_slot) == 16, "slot must be 16 bytes");
_Static_assert(offsetof(fl_slot, code) == 4 && offsetof(fl_slot, v) == 8, "slot layout");

/* FLEngine rodata の文言 → code 1..8。Python 側 fl_api._ERR の写像と整合させた暫定値
 * (実エンジンの数値は未確認。REPORT の未解決参照)。 */
enum {
    FL_OK = 0,
    FL_E_INVALID_VALUE = 1, /* "Invalid value"                                          → ValueError */
    FL_E_UNSPECIFIED = 2,   /* "Unspecified error" (未実装関数もここ)                   → RuntimeError */
    FL_E_UNSAFE = 3,        /* "Operation unsafe at current time"                       → RuntimeError */
    FL_E_RANGE = 4,         /* "Range error" / "Index out of range"                     → IndexError */
    FL_E_WRONG_PARAM = 5,   /* "Wrong number of function parameters or wrong parameter type" → TypeError */
    FL_E_LINKED_DEVICE = 6, /* "Linked device not assigned"                             → RuntimeError */
    FL_E_DEVICE = 7,        /* "Device not assigned"                                    → RuntimeError */
    FL_E_PLUGIN = 8,        /* "Plugin not valid"                                       → RuntimeError */
};

typedef struct fl_desc fl_desc;
typedef struct {
    const fl_slot *a;
    int n;
    fl_slot *ret;
} fl_call;

typedef int (*fl_handler)(fl_call *c); /* 0 = ok (ret 設定済み), 非 0 = FL エラー code (fl_err 済み) */

struct fl_desc {
    const char *mod, *name;
    char ret;           /* n None / i int / f float / b bool / s str / a handler 任せ */
    signed char np;     /* 署名上の引数数。-1 = 署名なし (handler が個数・型を検査) */
    signed char nmin;   /* 既定値なしの引数数 */
    const char *ptypes; /* i b f s a の列 */
    fl_handler h;       /* NULL = 未実装 */
};

extern const fl_desc fl_table[]; /* gen_provider.py 生成。添字 = fn_id */
extern const int fl_table_n;

int fl_err(fl_call *c, int code, const char *msg);
int fl_ret_none(fl_call *c);
int fl_ret_i(fl_call *c, int64_t v);
int fl_ret_b(fl_call *c, int v);
int fl_ret_d(fl_call *c, double v);
int fl_ret_s(fl_call *c, const char *s);
int fl_ret_json(fl_call *c, const char *json);

/* 引数取得。i が無い/None なら def。型不一致は fl_err(WRONG_PARAM) して非 0 */
int fl_a_int(fl_call *c, int i, int64_t def, int64_t *out);
int fl_a_dbl(fl_call *c, int i, double def, double *out);
int fl_a_str(fl_call *c, int i, const char **out);
int fl_a_cb(fl_call *c, int i, int64_t *out);

/* handler 定義: FL_H(mixer, getTrackName) { ... return fl_ret_s(c, ...); } */
#define FL_H(mod, name) int h_##mod##_##name(fl_call *c)

#define A_INT(i, def) ({ int64_t _v; int _e = fl_a_int(c, (i), (def), &_v); if (_e) return _e; _v; })
#define A_DBL(i, def) ({ double _v; int _e = fl_a_dbl(c, (i), (def), &_v); if (_e) return _e; _v; })
#define A_STR(i) ({ const char *_v; int _e = fl_a_str(c, (i), &_v); if (_e) return _e; _v; })

#endif
