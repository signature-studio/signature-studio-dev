#!/usr/bin/env python3
"""trap144_653f_probe_5280.py: trap 144 (OOB・function_44aeb0) の上流で、function_6539e0 に dsp_ippv2.dll (0x2572dc) を渡す
function_653f40 がどの呼出し元から走るかを採る IR 変種 (#5280 受入 2・診断用)。
  使い方: python3 trap144_653f_probe_5280.py <in.ll> <out.ll>
  in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
  記録 (guest 線形メモリ 0x11FF8400 以降。既存 probe の 0x11FF8000・0x11FF8200・0x11FF9000 と重ならない):
    +0   function_653f40 の entry 通過回数
    +8   function_653f40 の entry 時の global 18825448 (0 なら dsp_ippv2 側へ進む)
    +16  function_65c540 の entry 通過回数
    +24  function_65c540 → function_653f40 の通過回数
    +32  function_680610 → function_653f40 の通過回数
    +40  function_680610 の entry 通過回数
    +48〜+72 function_680610 の直接 call site 4 箇所 (2622504 の 1 件・2622232 の 3 件) の通過回数
    +80  function_653f40 → function_6539e0 (dsp_ippv2.dll) の通過回数
    +88  function_65c540 の entry 時のカウンタ 18825440 (減算前の値・0 なら 653f40 を呼ぶ)
  call site は元 IR の文字列で特定する (行番号は使わない)。"""
import re, sys

BASE = 0x11FF8400
SLOT = {
    'e653': 0, 'v653': 8, 'e65c': 16, 's65c': 24, 's680': 32, 'e680': 40,
    'm1': 48, 'm2': 56, 'm3': 64, 'm4': 72, 'dsp': 80, 'cnt65c': 88,
}
SITES = [
    ('s65c', 'call i64 @function_653f40(i64 %2, i64 %1)'),
    ('s680', 'call i64 @function_653f40(i64 %stack_var_8.0.reload, i64 0)'),
    ('m1', 'call i64 @function_680610(ptr nonnull inttoptr (i64 2622504 to ptr), i64 %29)'),
    ('m2', 'call i64 @function_680610(ptr nonnull inttoptr (i64 2622232 to ptr), i64 1)'),
    ('m3', 'call i64 @function_680610(ptr nonnull inttoptr (i64 2622232 to ptr), i64 %16)'),
    ('m4', 'call i64 @function_680610(ptr nonnull inttoptr (i64 2622232 to ptr), i64 %11)'),
    ('dsp', 'call i64 @function_6539e0(ptr getelementptr inbounds ([14 x i16], ptr inttoptr (i64 2454236 to ptr), i64 0, i64 0)'),
]
ENTRIES = {
    'dec_label_pc_653f40:': 'e653',
    'dec_label_pc_65c540:': 'e65c',
    'dec_label_pc_680610:': 'e680',
}
GLOBAL_LINE = 'dec_label_pc_653f40:'
DEF_FNS = ('function_653f40', 'function_65c540', 'function_680610', 'function_6539e0')


def slot(off):
    return 'inttoptr (i64 %d to ptr)' % (BASE + off)


def bump(tag, off):
    return [
        '  %%p%s_ld = load i64, ptr %s, align 8' % (tag, slot(off)),
        '  %%p%s_nx = add i64 %%p%s_ld, 1' % (tag, tag),
        '  store i64 %%p%s_nx, ptr %s, align 8' % (tag, slot(off)),
    ]


def main(src, dst):
    lines = open(src, errors='replace').read().split('\n')
    out = []
    counts = {}
    for i, l in enumerate(lines):
        s = l.strip()
        if s in ENTRIES:
            tag = ENTRIES[s]
            out.append(l)
            out.append('  ; trap144_653f probe entry %s' % tag)
            out += bump(tag, SLOT[tag])
            if tag == 'e65c':
                out.append('  %p65c_c = load i32, ptr inttoptr (i64 18825440 to ptr), align 4')
                out.append('  %p65c_w = zext i32 %p65c_c to i64')
                out.append('  store i64 %%p65c_w, ptr %s, align 8' % slot(SLOT['cnt65c']))
            if tag == 'e653':
                out.append('  %p653_g = load i64, ptr inttoptr (i64 18825448 to ptr), align 8')
                out.append('  store i64 %%p653_g, ptr %s, align 8' % slot(SLOT['v653']))
            counts[tag] = counts.get(tag, 0) + 1
            continue
        hit = next((t for t, text in SITES if text in l), None)
        if hit is not None:
            indent = l[:len(l) - len(l.lstrip())]
            out.append('  ; trap144_653f probe site %s' % hit)
            out += bump(hit, SLOT[hit])
            out.append(l)
            counts[hit] = counts.get(hit, 0) + 1
            continue
        out.append(l)
    need = {'e653': 1, 'e65c': 1, 'e680': 1, 's65c': 1, 's680': 1, 'm1': 1, 'm2': 1, 'm3': 1, 'm4': 1, 'dsp': 1}
    for k, n in need.items():
        if counts.get(k, 0) != n:
            sys.exit('[trap144_653f_probe_5280] %s の計装が %d 件 (期待 %d)' % (k, counts.get(k, 0), n))
    open(dst, 'w').write('\n'.join(out))
    print('[trap144_653f_probe_5280] 計装 %d 箇所 -> %s' % (sum(counts.values()), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
