#!/usr/bin/env python3
"""probe_alloca_942.py: alloca 適用後の boot trap (unit 56・function_8c6530) の引数の出所を記録する IR 変種を作る (#942 受入 1・2, 診断用)。
 使い方: python3 probe_alloca_942.py <base.ll> <out.ll>   (base は alloca 適用済みの IR)
 記録先は PROBE_BASE 以降 (probe_942.py の領域と重ならない)。関数 entry で hit を数え、引数を書く。
 function_8c7450 (テーブル参照 base+8*idx) は直近 RN 回の呼出しを ring (RING 以降・RS byte 刻み) に書く: +0 idx・+8 [obj+20]・+16 [obj+8]・+24 戻り値・+32 hit 番号・+40 obj。
 読み方は trap56_probe_942.mjs。記録は各関数の最後の entry (後の呼出しで上書きされる)。"""
import re, sys

PROBE_BASE = 0x11FFF600
SLOT = 64
RING = 0x100
RN = 32
RS = 48
SITES = [
    ('function_8c7450', 2, True),
    ('function_8c6530', 3, False),
]


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    for k, (name, nargs, deep) in enumerate(SITES):
        i = next(j for j, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(name), l))
        j = next(j for j in range(i + 1, len(lines)) if re.match(r'^[A-Za-z0-9_.$-]+:', lines[j]))
        base = PROBE_BASE + k * SLOT
        b = '%%dbg%d_b' % k
        ins = [
            '  %s = inttoptr i64 %d to ptr' % (b, base),
            '  %%dbg%d_h = load i64, ptr %s, align 8' % (k, b),
            '  %%dbg%d_h1 = add i64 %%dbg%d_h, 1' % (k, k),
            '  store i64 %%dbg%d_h1, ptr %s, align 8' % (k, b),
        ]
        for a in range(1, nargs + 1):
            ins.append('  %%dbg%d_p%d = getelementptr i8, ptr %s, i64 %d' % (k, a, b, 8 * a))
            ins.append('  store i64 %%arg%d, ptr %%dbg%d_p%d, align 8' % (a, k, a))
        if deep:
            ins += [
                '  %%dbg%d_o = add i64 %%arg1, 20' % k,
                '  %%dbg%d_op = inttoptr i64 %%dbg%d_o to ptr' % (k, k),
                '  %%dbg%d_n = load i32, ptr %%dbg%d_op, align 4' % (k, k),
                '  %%dbg%d_n64 = zext i32 %%dbg%d_n to i64' % (k, k),
                '  %%dbg%d_t = add i64 %%arg1, 8' % k,
                '  %%dbg%d_tp = inttoptr i64 %%dbg%d_t to ptr' % (k, k),
                '  %%dbg%d_tb = load i64, ptr %%dbg%d_tp, align 8' % (k, k),
                '  %%dbg%d_hm = and i64 %%dbg%d_h, %d' % (k, k, RN - 1),
                '  %%dbg%d_ho = mul i64 %%dbg%d_hm, %d' % (k, k, RS),
                '  %%dbg%d_ho2 = add i64 %%dbg%d_ho, %d' % (k, k, RING),
                '  %%dbg%d_e = getelementptr i8, ptr %s, i64 %%dbg%d_ho2' % (k, b, k),
                '  %%dbg%d_e0 = getelementptr i8, ptr %%dbg%d_e, i64 0' % (k, k),
                '  store i64 %%arg2, ptr %%dbg%d_e0, align 8' % k,
                '  %%dbg%d_e8 = getelementptr i8, ptr %%dbg%d_e, i64 8' % (k, k),
                '  store i64 %%dbg%d_n64, ptr %%dbg%d_e8, align 8' % (k, k),
                '  %%dbg%d_e16 = getelementptr i8, ptr %%dbg%d_e, i64 16' % (k, k),
                '  store i64 %%dbg%d_tb, ptr %%dbg%d_e16, align 8' % (k, k),
                '  %%dbg%d_e32 = getelementptr i8, ptr %%dbg%d_e, i64 32' % (k, k),
                '  store i64 %%dbg%d_h, ptr %%dbg%d_e32, align 8' % (k, k),
                '  %%dbg%d_e40 = getelementptr i8, ptr %%dbg%d_e, i64 40' % (k, k),
                '  store i64 %%arg1, ptr %%dbg%d_e40, align 8' % k,
            ]
        lines[j + 1:j + 1] = ins
        if deep:
            e = next(e for e in range(j, len(lines)) if lines[e] == '}')
            rets = [r for r in range(j, e) if re.match(r'^\s+ret i64 \S+$', lines[r])]
            for n, r in reversed(list(enumerate(rets))):
                v = lines[r].split()[-1]
                lines[r:r] = ['  %%dbg%d_rp%d = getelementptr i8, ptr %%dbg%d_e, i64 24' % (k, n, k),
                              '  store i64 %s, ptr %%dbg%d_rp%d, align 8' % (v, k, n)]
            print('[probe_alloca_942] %s ret sites: %d' % (name, len(rets)))
    open(dst, 'w').write('\n'.join(lines))
    print('[probe_alloca_942] %d sites -> %s' % (len(SITES), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
