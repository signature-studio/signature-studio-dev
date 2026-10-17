/* scen_kclp.h — #4413 (KH-91 #4153 と同範囲) ACFRegisterPlugin_kclp の 32bit 検索関数 (0x180f89cf0) を、経路フラグを指定して呼ぶ scenario。
 * 関数: find32(begin, end, value) -> 最初に value と一致する u32 の先頭ポインタ (無ければ end)。
 * 経路フラグ .data 0x182989344: bit5 が 1 なら ymm 経路、0 なら scalar 経路。trial 偶数 = ymm (0x20)、奇数 = scalar (0x2 = ファイル値)。
 * フラグは arena の外 (image) にあるため vectors.bin には入らない。wasm 側 (compare.mjs) は同じ値を同じ trial で書き込むこと。
 * native 側は C の参照実装と照合し、不一致を stderr に出す (経路ごとの意味の正しさを native で先に確認する)。
 */
#include "scen_common.h"
#define KC_FIND32 0x180f89cf0UL
#define KC_FLAG_A 0x182989344UL
static void trial_kclp(int t) {
    int n = RI(0, 40);
    u32* buf = A((size_t)(n ? n : 1) * 4);
    REGION("buf", buf, (size_t)n * 4);
    for (int i = 0; i < n; i++) buf[i] = R32() % 8;
    u32 value = R32() % 8;
    *(volatile u32*)KC_FLAG_A = (t & 1) ? 0x2u : 0x20u;
    u8* end = (u8*)buf + (size_t)n * 4;
    u64 got = C3(KC_FIND32, RET_I64, buf, end, value);
    u8* want = end;
    for (int i = 0; i < n; i++) if (buf[i] == value) { want = (u8*)(buf + i); break; }
    if (got != (u64)(uintptr_t)want) fprintf(stderr, "kclp mismatch trial=%d flag=%s n=%d\n", t, (t & 1) ? "scalar" : "ymm", n);
}
