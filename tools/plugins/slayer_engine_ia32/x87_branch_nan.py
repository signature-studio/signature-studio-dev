#!/usr/bin/env python3
"""x87_branch_nan.py: NaN との比較 (fcomp → fnstsw → test ah) の分岐を実 x87 と模型 (ott_x87.h の x87_fcom) で突合する (#4817 PLG-G2-63)。

  python3 x87_branch_nan.py

 入力の組 (a, b): a は NaN (±qNaN・sNaN・ペイロード違い)・±inf・±0・非正規・通常値、b は同じ集合。
 native: 実 x87 で fld a; fcomp b; fnstsw ax の結果 (C3/C2/C0) を取る。
 model : tools/ott/rt/ott_x87.h の x87_fcom をそのまま呼び、ott_fsw を読む (lift の fcomp と同じ経路)。
 判定: 全組で C3/C2/C0 が一致すること (不一致 0 件で PASS)。 さらに lift の分岐 `test ah, 0x41` → `je` の
 真偽 (ah & 0x41 == 0) が一致することを数える。
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RT = os.path.normpath(os.path.join(HERE, '..', '..', 'ott', 'rt'))

VALS = [
    0x7FC00000, 0xFFC00000, 0x7FC00001, 0x7F800001, 0xFF800001,   # NaN (qNaN・-qNaN・ペイロード違い・sNaN)
    0x7F800000, 0xFF800000,                                       # +inf / -inf
    0x00000000, 0x80000000,                                       # +0 / -0
    0x00000001, 0x007FFFFF,                                       # 非正規
    0x3F800000, 0xBF800000, 0x40490FDB,                           # 1.0 / -1.0 / 3.14159
]

NATIVE = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
static uint16_t cmp(uint32_t a, uint32_t b) {
    volatile float x, y; uint16_t sw;
    memcpy((void*)&x, &a, 4); memcpy((void*)&y, &b, 4);
    __asm__ volatile("fninit\n\tflds %1\n\tfcomps %2\n\tfnstsw %%ax\n\tmovw %%ax, %0\n\tfstp %%st(0)"
                     : "=m"(sw) : "m"(x), "m"(y) : "eax", "st", "memory");
    return sw & 0x4500;
}
int main(void) {
    uint32_t v[] = {@VALS@};
    int n = (int)(sizeof v / sizeof v[0]);
    for (int i = 0; i < n; i++) for (int j = 0; j < n; j++)
        printf("%d %d %04x\n", i, j, (unsigned)cmp(v[i], v[j]));
    return 0;
}
'''

MODEL = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "ott_x87.h"
int main(void) {
    uint32_t v[] = {@VALS@};
    int n = (int)(sizeof v / sizeof v[0]);
    for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) {
        float fa, fb; memcpy(&fa, &v[i], 4); memcpy(&fb, &v[j], 4);
        ott_fsw = 0;
        x87_fcom((double)fa, (double)fb);
        printf("%d %d %04x\n", i, j, (unsigned)(ott_fsw & 0x4500));
    }
    return 0;
}
'''


def run_c(src_fmt, name, tmp, extra):
    src = src_fmt.replace('@VALS@', ', '.join('0x%08xu' % v for v in VALS))
    c = os.path.join(tmp, name + '.c')
    exe = os.path.join(tmp, name)
    open(c, 'w').write(src)
    subprocess.run(['gcc', '-O0', '-w'] + extra + ['-o', exe, c], check=True)
    return subprocess.run([exe], capture_output=True, text=True, check=True).stdout


def table(text):
    t = {}
    for ln in text.split('\n'):
        p = ln.split()
        if len(p) == 3:
            t[(int(p[0]), int(p[1]))] = int(p[2], 16)
    return t


def is_nan(u):
    return (u & 0x7F800000) == 0x7F800000 and (u & 0x7FFFFF) != 0


def main():
    with tempfile.TemporaryDirectory() as tmp:
        nat = table(run_c(NATIVE, 'nat', tmp, []))
        mod = table(run_c(MODEL, 'mod', tmp, ['-I', RT]))
    n = len(VALS)
    diff = [k for k in nat if nat[k] != mod[k]]
    nan_pairs = [k for k in nat if is_nan(VALS[k[0]]) or is_nan(VALS[k[1]])]
    jump_diff = sum(1 for k in nat if ((nat[k] >> 8) & 0x41 == 0) != ((mod[k] >> 8) & 0x41 == 0))
    nan_unord = sum(1 for k in nan_pairs if nat[k] == 0x4500)
    print('[branch] 組 %d (値 %d 種 x %d 種)、NaN を含む組 %d' % (n * n, n, n, len(nan_pairs)))
    print('[branch] native と model の C3/C2/C0 の不一致 %d 組 (期待 0)' % len(diff))
    print('[branch] NaN を含む組のうち native が unordered (C3=C2=C0=1) の数 %d / %d' % (nan_unord, len(nan_pairs)))
    print('[branch] test ah,0x41 → je の分岐 (真偽) の不一致 %d 組 (期待 0)' % jump_diff)
    if diff or jump_diff:
        for k in diff[:10]:
            print('[branch]   (%d,%d) native %04x model %04x' % (k[0], k[1], nat[k], mod[k]))
        print('[branch] FAIL')
        sys.exit(1)
    print('[branch] PASS')


if __name__ == '__main__':
    main()
