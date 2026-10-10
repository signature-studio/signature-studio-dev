/* icall_simd_extra.c — m11_simd2.py が未実装 (fail-fast stub) にする SSE2 helper の補完 (OTT CRT 数学で使用)。
 * route スクリプトは m11_simd2 出力から同名 stub 定義を除いてからこれをリンクする。 */
#include <stdint.h>
#include <string.h>
#include <math.h>
typedef unsigned __int128 u128;
typedef unsigned long long u64;
static double asd_(u64 b) { double d; memcpy(&d, &b, 8); return d; }
/* cmplesd xmm, xmm/m64: low64 = (a0 <= b) ? ~0 : 0 ; high64 は a のまま */
u128 __asm_cmplesd(u128 a, u64 b) { u64 hi = (u64)(a >> 64); double x = asd_((u64)a), y = asd_(b); u64 m = (x <= y) ? ~0ull : 0ull; return ((u128)hi << 64) | m; }
/* cmpnltsd: !(a0 < b) (NaN なら true) */
u128 __asm_cmpnltsd(u128 a, u64 b) { u64 hi = (u64)(a >> 64); double x = asd_((u64)a), y = asd_(b); u64 m = !(x < y) ? ~0ull : 0ull; return ((u128)hi << 64) | m; }
/* cvttpd2dq xmm, xmm: 2 x f64 → 2 x i32 (truncate, 範囲外/NaN は 0x80000000), 上位 64bit = 0 */
static uint32_t tt(double d) { if (d != d || d >= 2147483648.0 || d < -2147483648.0) return 0x80000000u; return (uint32_t)(int32_t)d; }
u128 __asm_cvttpd2dq(u128 a) { u64 lo = (u64)a, hi = (u64)(a >> 64); return (u128)(((u64)tt(asd_(hi)) << 32) | tt(asd_(lo))); }
/* cvtpd2dq: 2 x f64 → 2 x i32 (現在の丸め=最近接偶数), 範囲外/NaN は 0x80000000, 上位 64bit = 0 */
static uint32_t rn(double d) { if (d != d || d >= 2147483647.5 || d <= -2147483648.5) return 0x80000000u; return (uint32_t)(int32_t)nearbyint(d); }
u128 __asm_cvtpd2dq(u128 a) { u64 lo = (u64)a, hi = (u64)(a >> 64); return (u128)(((u64)rn(asd_(hi)) << 32) | rn(asd_(lo))); }
u128 __asm_sqrtpd(u128 a) { u64 lo = (u64)a, hi = (u64)(a >> 64); double x = sqrt(asd_(lo)), y = sqrt(asd_(hi)); u64 l, h; memcpy(&l, &x, 8); memcpy(&h, &y, 8); return ((u128)h << 64) | l; }
