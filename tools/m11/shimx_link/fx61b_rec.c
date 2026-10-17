/* #5855 (SHX-T61 次段) 計装用: 親 function_448490 の外側 loop 入口が書く @fx61b_buf を読む。
 * IR に @fx61b_buf があるときだけ build.sh --trace がリンクする (既定の trace は変えない)。
 * buf[0] = 入口の通過回数, buf[1] = 上限 %9 (下位 32 bit), buf[2] = 添字 -32.0 の直近値, buf[3] = 添字 -32.2 の直近値。 */
#include <stdint.h>
#include <emscripten.h>

extern int32_t fx61b_buf[4];

EMSCRIPTEN_KEEPALIVE int32_t fx61b_count(void) { return fx61b_buf[0]; }
EMSCRIPTEN_KEEPALIVE int32_t fx61b_lim(void) { return fx61b_buf[1]; }
EMSCRIPTEN_KEEPALIVE int32_t fx61b_idx(void) { return fx61b_buf[2]; }
EMSCRIPTEN_KEEPALIVE int32_t fx61b_idx2(void) { return fx61b_buf[3]; }
