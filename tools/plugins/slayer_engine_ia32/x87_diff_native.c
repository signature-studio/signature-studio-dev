/* x87_diff_native.c — x87 差分試験の参照側 (実 x87 命令)。
 * 各 op は generator (x87_diff.py) が出した機械語 (.byte) をそのまま実行する。 中間値は実 FPU の 80bit。
 * ビルド: x87_diff.py が work/x87/ に生成する x87_native_ops.inc を -I で渡す (gcc -O1 -w)。 */
#include <stdint.h>
#include <string.h>
#include "x87_native_ops.inc"

static void ops_init(void) { __asm__ volatile(".byte 0xdb,0xe3" ::: "memory"); }   /* fninit: FCW=037f */

static uint16_t ops_fsw(void) {
    unsigned long ax;
    __asm__ volatile(".byte 0xdf,0xe0" : "=a"(ax) :: "memory");   /* fnstsw ax */
    return (uint16_t)ax;
}

/* fnsave (108 B: 28 B の環境 + ST(0..7) 各 10 B) → 各 80bit を fldt で読み、fstpl で double に丸める (RN) */
static void ops_final(double* out, int d) {
    uint8_t buf[108] __attribute__((aligned(16)));
    __asm__ volatile("mov %0, %%rax\n\t.byte 0xdd,0x30" :: "r"(buf) : "rax", "memory");
    for (int j = 0; j < d; j++)
        __asm__ volatile("mov %0, %%rax\n\t.byte 0xdb,0x28\n\t"
                         "mov %1, %%rax\n\t.byte 0xdd,0x18" :: "r"(buf + 28 + 10 * j), "r"(out + j) : "rax", "memory");
}

#include "x87_diff_main.h"
