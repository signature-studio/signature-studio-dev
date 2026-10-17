/* scen_kclp_b.h — #4413 (KH-98) ACFRegisterPlugin_kclp の 16bit 検索関数 (0x180fb6124) を、経路フラグ B を指定して呼ぶ scenario。
 * 関数: 0 終端の u16 列の長さを返す (wcslen 相当)。経路フラグ .data 0x182989340 (i32):
 *   >= 5 → ymm 経路 (vpcmpeqw ymm)、1..4 → SSE 経路 (pcmpeqw xmm)、<= 0 → scalar 経路。
 * trial は 3 経路を循環させる (t % 3: 0 = ymm 0x5, 1 = SSE 0x1, 2 = scalar 0x0)。
 * フラグは arena の外 (image) にあるため vectors.bin には入らない。wasm 側 (compare.mjs --path-flags-b) は同じ値を同じ trial で書き込むこと。
 * native 側は C の参照実装と照合し、不一致を stderr に出す。
 */
#include "scen_common.h"
#define KC_FN_B 0x180fb6124UL
#define KC_FLAG_B 0x182989340UL
static void trial_kclp_b(int t) {
    static const u32 flags[3] = {0x5u, 0x1u, 0x0u};
    int n = RI(0, 40);
    u16* buf = A((size_t)(n + 1) * 2);
    REGION("buf", buf, (size_t)(n + 1) * 2);
    for (int i = 0; i < n; i++) buf[i] = (u16)(1 + R32() % 7);
    buf[n] = 0;
    u32 flag = flags[t % 3];
    *(volatile u32*)KC_FLAG_B = flag;
    u64 got = C1(KC_FN_B, RET_I64, buf);
    u64 want = (u64)n;
    if (got != want) fprintf(stderr, "kclp_b mismatch trial=%d flag=%#x n=%d got=%llu\n", t, flag, n, (unsigned long long)got);
}
