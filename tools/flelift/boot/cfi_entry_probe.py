#!/usr/bin/env python3
# cfi_entry_probe.py — #4464 [WIN-51]: CFI 経路 5 本の入口レジスタ (rcx・rdx・dl) を記録する probe を生成 C に入れる。
# 生成物 (work/boot/lift/*.c) だけを書き換える。repo の lift 出力は変えない。
# 使い方: python3 cfi_entry_probe.py <lift_dir>   (既定 tools/flelift/work/boot/lift)
# 出力: <lift_dir>/fle_lifted_s*.c の該当 f_<VA> の先頭に fle_cfi_log(VA, rcx, rdx, dl) を挿入する。
import glob
import os
import re
import sys

VAS = [0x1375990, 0x13752f0, 0x1105350, 0x5af120, 0x410320]
HERE = os.path.dirname(os.path.abspath(__file__))
LIFT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'boot', 'lift')

hook = (
    'extern void fle_cfi_log(unsigned va, unsigned long long rcx, unsigned long long rdx, unsigned dl);\n'
)
LOGDEF = (
    '\n#include <stdio.h>\n'
    'void fle_cfi_log(unsigned va, unsigned long long rcx, unsigned long long rdx, unsigned dl) {\n'
    '  fprintf(stderr, "[cfi] va=0x%x rcx=0x%llx rdx=0x%llx dl=0x%x\\n", va, rcx, rdx, dl);\n'
    '}\n'
)


def main():
    files = sorted(glob.glob(os.path.join(LIFT, 'fle_lifted_s*.c')))
    n = {v: 0 for v in VAS}
    for path in files:
        src = open(path).read()
        changed = False
        for va in VAS:
            pat = re.compile(r'^void f_%x\(void\) \{\n' % va, re.M)
            m = pat.search(src)
            if not m:
                continue
            ins = ('  fle_cfi_log(0x%x, R[1], R[2], (unsigned)(R[2] & 0xff));\n' % va)
            src = src[:m.end()] + ins + src[m.end():]
            n[va] += 1
            changed = True
        icall_old = '  { uint64_t t_ = LD64((R[0] + 0xffffffffffffffd0ULL)); R[RSP] -= 8; ST64(R[RSP], 0x410331ULL); ott_dispatch(t_); }'
        icall_new = ('  { uint64_t t_ = LD64((R[0] + 0xffffffffffffffd0ULL)); fprintf(stderr, "[icall] rax=0x%llx target=0x%llx\\n", '
                     '(unsigned long long)R[0], (unsigned long long)t_); R[RSP] -= 8; ST64(R[RSP], 0x410331ULL); ott_dispatch(t_); }')
        if icall_old in src:
            src = src.replace(icall_old, icall_new)
            n['icall'] = n.get('icall', 0) + 1
            changed = True
        if path.endswith('fle_lifted_s0.c'):
            src += LOGDEF
            changed = True
        if changed:
            src = '#include <stdio.h>\n' + hook + src
            open(path, 'w').write(src)
    for va in VAS:
        print('f_%x probed %d' % (va, n[va]))
    if any(v != 1 for v in n.values()):
        sys.exit('expected exactly 1 definition per VA, got %s' % n)


if __name__ == '__main__':
    main()
