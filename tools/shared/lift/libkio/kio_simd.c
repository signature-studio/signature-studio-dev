/* RetDec が lift できなかった SSE 命令の __asm_* helper (libkio 15 関数分; 宣言型は lift IR の declare に一致)
 * 規約は tools/m6..m11 の msimd と同じ: i128 = xmm レジスタ全体, 浮動小数は IEEE round-to-nearest。 */
#include <stdint.h>
#include <string.h>
typedef unsigned __int128 u128;
static float lane0f(u128 a) { uint32_t u = (uint32_t)a; float f; memcpy(&f, &u, 4); return f; }
u128 __asm_movq(uint64_t a) { return (u128)a; }
u128 __asm_movd(uint32_t a) { return (u128)a; }
u128 __asm_movaps(u128 a) { return a; }
/* minss dst,src : dst.lo32 = (dst < src) ? dst : src ; 上位は dst を保持 */
u128 __asm_minss(u128 a, u128 b) {
  float x = lane0f(a), y = lane0f(b); uint32_t r;
  float m = (x < y) ? x : y; memcpy(&r, &m, 4);
  return (a & ~(u128)0xffffffffu) | r;
}
/* cvttss2si r64,xmm : 範囲外/NaN は 0x8000000000000000 (x86 "integer indefinite") */
uint64_t __asm_cvttss2si(u128 a) {
  float f = lane0f(a);
  if (!(f > -9223372036854775808.0f && f < 9223372036854775808.0f)) return 0x8000000000000000ull;
  return (uint64_t)(int64_t)f;
}
/* ucomiss は EFLAGS を書く。RetDec は flags 結果を IR に接続しない (M6 REPORT P1 と同現象) -> ここでは no-op */
void __asm_ucomiss(u128 a, u128 b) { (void)a; (void)b; }
