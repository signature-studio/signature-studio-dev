/* x87_diff_lowered.c — x87 差分試験の lowered 側。 op は x64c (ia32) が lift した C (x87_lowered_ops.inc) を実行する。
 * ビルド: x87_diff.py が work/x87/ に生成する x87_lowered_ops.inc を -I で渡し、tools/ott/rt/ott_cpu.c とリンクする。 */
#include "ott_cpu.h"
#include "ott_x87.h"
#include "x87_lowered_ops.inc"

uint64_t ott_gbase;   /* ott_cpu.c の参照先 (本体は ott_glue.c)。 試験は相対化モードを使わない */

static void ops_init(void) {
    memset(ott_fst, 0, sizeof ott_fst);
    ott_ftop = 0; ott_fcw = 0x037f; ott_fsw = 0;
}

static uint16_t ops_fsw(void) { return x87_fsw(); }

static void ops_final(double* out, int d) {
    for (int j = 0; j < d; j++) out[j] = x87_st((unsigned)j);
}

#include "x87_diff_main.h"
