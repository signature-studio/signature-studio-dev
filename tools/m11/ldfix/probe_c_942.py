#!/usr/bin/env python3
"""probe_c_942.py: m11_ov.c の C 版 function_4133f0・function_418190 の entry に記録を入れた複製を作る (#942 受入 1・2, 診断用)。
 使い方: python3 probe_c_942.py <m11_ov.c> <out.c>   (out.c は stage4 用の作業ツリーの m11_ov.c に置く。repo の m11_ov.c は変えない)
 記録先 (線形メモリ固定番地): 0x11FFF400 = 4133f0 (+0 hit, +8 dest, +16 src)、0x11FFF420 = 418190 (+0 hit, +8 dest, +16 *dest)。
 差し替え手順は REPORT_942_TRAPSITE.md §7。"""
import sys

PATCH = {
    'unsigned long long function_4133f0(unsigned long long dest, unsigned long long src) {':
        '    { volatile u64 *pc = (volatile u64*)(uintptr_t)0x11FFF400; pc[0]++; pc[1] = dest; pc[2] = src; }',
    'unsigned long long function_418190(unsigned long long dest, unsigned long long ti, unsigned long long unused) {':
        '    { volatile u64 *pc = (volatile u64*)(uintptr_t)0x11FFF420; pc[0]++; pc[1] = dest; pc[2] = Q(dest); }',
}


def main(src, dst):
    out, hit = [], 0
    for line in open(src).read().split('\n'):
        out.append(line)
        if line in PATCH:
            out.append(PATCH[line])
            hit += 1
    assert hit == len(PATCH), 'patch 対象が %d 件 (想定 %d)' % (hit, len(PATCH))
    open(dst, 'w').write('\n'.join(out))
    print('[probe_c_942] %d functions -> %s' % (hit, dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
