/* #5855 (SHX-T61) 計装用: callee function_4483f0 の入口が書く @fx61_buf (IR 側の記録) を読み、標準エラーへ出す。
 * IR に @fx61_buf があるときだけ build.sh --trace がリンクする (既定の trace は変えない)。
 * buf[0] = 呼出し回数, buf[1] = 直近の this, buf[2] = 直近の +0x4c, buf[3] = 直近の +0x48。
 * 呼出しごとの値は取らない (IR 側は直近の値だけを残す)。hang の位置は、回数と直近の値を
 * hang 後の時点で読んで判断する。 */
#include <stdint.h>
#include <stdio.h>
#include <emscripten.h>

extern int32_t fx61_buf[4];

EMSCRIPTEN_KEEPALIVE int32_t fx61_count(void) { return fx61_buf[0]; }
EMSCRIPTEN_KEEPALIVE uint32_t fx61_self(void) { return (uint32_t)fx61_buf[1]; }
EMSCRIPTEN_KEEPALIVE int32_t fx61_c4c(void) { return fx61_buf[2]; }
EMSCRIPTEN_KEEPALIVE int32_t fx61_c48(void) { return fx61_buf[3]; }
