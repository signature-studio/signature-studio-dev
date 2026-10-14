#!/usr/bin/env python3
"""probe_942.py: trap 6 箇所の関数 entry に引数の記録を入れた IR 変種を作る (#942 受入 1・2, 診断用)。
 使い方: python3 probe_942.py <base.ll> <out.ll>
 記録先は線形メモリ固定番地 PROBE_BASE + k*SLOT (k = SITES の番号): +0 hit 回数, +8/+16/+24 = arg1/arg2/arg3 (entry 時点), +32 = 戻り値 (RET_SITES のみ・ret の直前で上書き)。
 注: 4133f0 と 418190 は m11_ov.c の C 転記で置換されるため、IR 版への probe は実行されない (hit 0 になる)。
 読み方は trap_probe_942.mjs。e2e の経路 (stage4.sh の既定) には入らない。"""
import re, sys

PROBE_BASE = 0x11FFF000
SLOT = 64
SITES = [
    ('function_418190', 3),
    ('function_4133f0', 2),
    ('function_409c80', 3),
    ('function_407e20__lifted', 1),
    ('function_412e40', 2),
    ('function_8c6530', 3),
    ('function_412c20', 1),
]
RET_SITES = {'function_412c20'}


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    for k, (name, nargs) in enumerate(SITES):
        i = next(j for j, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(name), l))
        j = next(j for j in range(i + 1, len(lines)) if re.match(r'^[A-Za-z0-9_.$-]+:', lines[j]))
        base = PROBE_BASE + k * SLOT
        ins = [
            '  %%dbg%d_b = inttoptr i64 %d to ptr' % (k, base),
            '  %%dbg%d_h = load i64, ptr %%dbg%d_b, align 8' % (k, k),
            '  %%dbg%d_h1 = add i64 %%dbg%d_h, 1' % (k, k),
            '  store i64 %%dbg%d_h1, ptr %%dbg%d_b, align 8' % (k, k),
        ]
        for a in range(1, nargs + 1):
            ins.append('  %%dbg%d_p%d = getelementptr i8, ptr %%dbg%d_b, i64 %d' % (k, a, k, 8 * a))
            ins.append('  store i64 %%arg%d, ptr %%dbg%d_p%d, align 8' % (a, k, a))
        lines[j + 1:j + 1] = ins
        if name in RET_SITES:
            e = next(e for e in range(j, len(lines)) if lines[e] == '}')
            rets = [r for r in range(j, e) if re.match(r'^\s+ret i64 \S+$', lines[r])]
            for n, r in reversed(list(enumerate(rets))):
                v = lines[r].split()[-1]
                lines[r:r] = ['  %%dbg%d_rp%d = getelementptr i8, ptr %%dbg%d_b, i64 32' % (k, n, k),
                              '  store i64 %s, ptr %%dbg%d_rp%d, align 8' % (v, k, n)]
            print('[probe_942] %s ret sites: %d' % (name, len(rets)))
    open(dst, 'w').write('\n'.join(lines))
    print('[probe_942] %d sites -> %s' % (len(SITES), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
