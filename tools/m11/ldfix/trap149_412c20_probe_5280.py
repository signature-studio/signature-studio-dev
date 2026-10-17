#!/usr/bin/env python3
"""trap149_412c20_probe_5280.py: trap 149 (OOB・function_412e40) の上流で、function_412c20 が戻り値 0 となる由来 (arg1 の値) を採る
IR 変種 (#5280 受入 3・診断用)。
  使い方: python3 trap149_412c20_probe_5280.py <in.ll> <out.ll>
  in.ll は prod fix の IR (prod_order_3608.sh h_nor8b fix ... が作る work/p3608/h_nor8b/prod.ll) を想定する。
  記録 (guest 線形メモリ 0x11FF8500 以降。既存 probe の 0x11FF8000・0x11FF8200・0x11FF8400・0x11FF9000 と重ならない):
    +0   function_4136a0 の entry 通過回数
    +8   function_4136a0 の entry 時の arg1 (オブジェクト)
    +16  function_4136a0 → function_412c20 の通過回数
    +24  function_412c20 の entry 通過回数
    +32  function_412c20 の entry 時の arg1 (長さ・0 以下なら戻り値 0)
    +40  function_412c20 の entry で arg1 を i32 の符号付きで見て 1 未満 (IR の枝 %3・戻り値 0 になる) の回数
    +48  function_412c20 の全 return の回数 (戻り値 0 の回数ではない・参考)
    +56  function_412e40 の entry 時の arg1 (0x10aa1418 側の値)
    +64  function_412e40 の entry 通過回数
    +72  function_4136a0 の 412c20 呼出し元の直接 call site (119255 行相当) の通過回数
  call site は元 IR の文字列で特定する (行番号は使わない)。"""
import re, sys

BASE = 0x11FF8500
SLOT = {
    'e4136': 0, 'a4136': 8, 'c4136': 16, 'e412c': 24, 'a412c': 32, 'z412c': 40, 'z412c_ret': 48,
    'a412e': 56, 'e412e': 64, 'site': 72, 'len4136': 80,
}
SPAN = 88


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
    cnt = {}

    def fn_range(name):
        s = next(i for i, l in enumerate(lines) if re.match(r'^define .*@%s\(' % re.escape(name), l))
        e = next(i for i in range(s, len(lines)) if lines[i] == '}')
        return s, e

    s4136, e4136 = fn_range('function_4136a0')
    s412c, e412c = fn_range('function_412c20')
    s412e, e412e = fn_range('function_412e40')
    for i, l in enumerate(lines):
        s = l.strip()
        if s == 'dec_label_pc_4136a0:' and s4136 <= i <= e4136:
            out.append(l)
            out.append('  ; trap149_412c20 probe 4136a0 entry')
            out += bump('e4136', SLOT['e4136'])
            out.append('  store i64 %%arg1, ptr %s, align 8' % slot(SLOT['a4136']))
            out.append('  %p4136_lp = add i64 %arg1, -4')
            out.append('  %p4136_lq = inttoptr i64 %p4136_lp to ptr')
            out.append('  %p4136_lv = load i32, ptr %p4136_lq, align 4')
            out.append('  %p4136_lw = zext i32 %p4136_lv to i64')
            out.append('  store i64 %p4136_lw, ptr ' + slot(SLOT['len4136']) + ', align 8')
            cnt['e4136'] = cnt.get('e4136', 0) + 1
            continue
        if s == 'dec_label_pc_412c20:' and s412c <= i <= e412c:
            out.append(l)
            out.append('  ; trap149_412c20 probe 412c20 entry')
            out += bump('e412c', SLOT['e412c'])
            out.append('  store i64 %%arg1, ptr %s, align 8' % slot(SLOT['a412c']))
            out.append('  %p412c_t = trunc i64 %arg1 to i32')
            out.append('  %p412c_z = icmp slt i32 %p412c_t, 1')
            out.append('  %p412c_zi = zext i1 %p412c_z to i64')
            out.append('  %p412c_zl = load i64, ptr ' + slot(SLOT['z412c']) + ', align 8')
            out.append('  %p412c_zn = add i64 %p412c_zl, %p412c_zi')
            out.append('  store i64 %p412c_zn, ptr ' + slot(SLOT['z412c']) + ', align 8')
            cnt['e412c'] = cnt.get('e412c', 0) + 1
            continue
        if s.startswith('dec_label_pc_412c79:') and s412c <= i <= e412c:
            out.append(l)
            out.append('  ; trap149_412c20 probe 412c20 return 0 path')
            out += bump('z412c_ret', SLOT['z412c_ret'])
            cnt['z412c_ret'] = cnt.get('z412c_ret', 0) + 1
            continue
        if s == 'dec_label_pc_412e40:' and s412e <= i <= e412e:
            out.append(l)
            out.append('  ; trap149_412c20 probe 412e40 entry')
            out += bump('e412e', SLOT['e412e'])
            out.append('  store i64 %%arg1, ptr %s, align 8' % slot(SLOT['a412e']))
            cnt['e412e'] = cnt.get('e412e', 0) + 1
            continue
        if s4136 <= i <= e4136 and 'call i64 @function_412c20(i64 %8)' in l:
            indent = l[:len(l) - len(l.lstrip())]
            out.append('  ; trap149_412c20 probe 4136a0 -> 412c20')
            out += bump('c4136', SLOT['c4136'])
            out.append(l)
            cnt['c4136'] = cnt.get('c4136', 0) + 1
            continue
        out.append(l)
    need = {'e4136': 1, 'e412c': 1, 'e412e': 1, 'c4136': 1}
    for k, n in need.items():
        if cnt.get(k, 0) != n:
            sys.exit('[trap149_412c20_probe_5280] %s の計装が %d 件 (期待 %d)' % (k, cnt.get(k, 0), n))
    open(dst, 'w').write('\n'.join(out))
    print('[trap149_412c20_probe_5280] 計装 %d 箇所 -> %s' % (sum(cnt.values()), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
