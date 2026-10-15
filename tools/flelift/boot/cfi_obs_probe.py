#!/usr/bin/env python3
# cfi_obs_probe.py — CFI 経路 (0x1375990 → 0x13752f0 → 0x1105350 → 0x5af120 → 0x410320) の入口で rcx/rdx/rax を記録する probe を生成する (#4464 / #4384)。
# 使い方: python3 tools/flelift/boot/cfi_obs_probe.py <lift dir> <出力 dir>   (既定の lift dir: tools/flelift/work/boot/lift)
# 出力 dir は lift の複製 (fle_lifted_s*.c に probe を入れたもの)。build.sh は FLE_LIFT_DIR=<出力 dir> で読む。
# 生成物のみ・commit しない。元の lift は書き換えない。
import re
import shutil
import sys
from pathlib import Path

SITES = {  # ファイル名: [(関数の入口ラベル, VA)]
    'fle_lifted_s7.c': [('L_1375990', 0x1375990)],
    'fle_lifted_s3.c': [('L_13752f0', 0x13752f0)],
    'fle_lifted_s6.c': [('L_1105350', 0x1105350)],
    'fle_lifted_s2.c': [('L_5af120', 0x5af120)],
    'fle_lifted_s4.c': [('L_410320', 0x410320)],
}
CALL_SITE = ('fle_lifted_s4.c', 'R[RSP] -= 8; ST64(R[RSP], 0x410331ULL); ott_dispatch(t_); }', 0x41032e)
PROTO = 'void fle_cfi_obs(uint32_t va, uint64_t rcx, uint64_t rdx, uint64_t rax, uint64_t t);'
IMPL = ('#include <stdio.h>\n'
        'void fle_cfi_obs(uint32_t va, uint64_t rcx, uint64_t rdx, uint64_t rax, uint64_t t) {\n'
        '  fprintf(stderr, "CFIOBS va=0x%x rcx=0x%llx rdx=0x%llx rax=0x%llx t=0x%llx\\n", va,\n'
        '          (unsigned long long)rcx, (unsigned long long)rdx, (unsigned long long)rax, (unsigned long long)t);\n'
        '}\n')


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'tools/flelift/work/boot/lift')
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else 'tools/flelift/work/boot/lift_cfi_probe')
    if not (src / 'fle_lifted_s0.c').exists():
        print(f'[cfi_obs_probe] lift が無い: {src} (先に fle6_measure.sh を実行する)', file=sys.stderr)
        return 2
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for name in sorted(set(SITES) | {CALL_SITE[0]}):
        text = (dst / name).read_text()
        text = text.replace('#include "fle_cpu.h"', '#include "fle_cpu.h"\n' + PROTO, 1)
        for label, va in SITES.get(name, []):
            hit = f'{label}:;'
            if text.count(hit) != 1:
                print(f'[cfi_obs_probe] {name}: {hit} が {text.count(hit)} 件', file=sys.stderr)
                return 3
            extra = f' fle_cfi_obs(0x{va:x}, R[1], R[2], R[0], LD64(0x1104e30ULL));' if va == 0x13752f0 else f' fle_cfi_obs(0x{va:x}, R[1], R[2], R[0], 0);'
            text = text.replace(hit, f'{hit}{extra}')
        if name == CALL_SITE[0]:
            old = CALL_SITE[1]
            if text.count(old) != 1:
                print(f'[cfi_obs_probe] {name}: call 行が {text.count(old)} 件', file=sys.stderr)
                return 3
            text = text.replace(old, f'fle_cfi_obs(0x{CALL_SITE[2]:x}, R[1], R[2], R[0], t_); {old}')
        (dst / name).write_text(text)
    with (dst / 'fle_lifted_s0.c').open('a') as fh:
        fh.write('\n' + IMPL)
    print(f'[cfi_obs_probe] probe を {dst} に生成 (site {len(SITES)} + call 1)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
