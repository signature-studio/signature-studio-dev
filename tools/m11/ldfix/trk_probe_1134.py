#!/usr/bin/env python3
"""trk_probe_1134.py — #1134: tracker-no-deref 3 関数 (75a180・db6480・dc27c0) と 5c44b0 (none) の記号実行の状態を出す。
使い方 (tools/m11 で実行): python3 ldfix/trk_probe_1134.py  (入力: work/boot_final3.ll・work/m11_image.bin・work/boot*.drc.config.json)
出力: 関数ごとの entry 直線部の sslot (1 回だけ書かれる frame home)・ループ先頭ブロックの有無・f3c_track の deref 一覧。"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

text = open('work/boot_final3.ll', errors='replace').read()
mach = ImageMachine('work/m11_image.bin', 'work/boot*.drc.config.json')
for x in ldfix.DEF_RE.finditer(text):
    ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
for k in sys.argv[1:] or ['75a180', 'db6480', 'dc27c0', '5c44b0']:
    va = int(k, 16)
    body = re.search(r'^define [^\n]*@function_%s\(.*?\n}\n' % k, text, re.M | re.S).group(0)
    labs = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    mach.cover(va, max(labs))
    fv = FnMach(mach, va, labs)
    sreg, sslot = ldfix._f3c_static_state(fv.cs, fv.ins)
    _l, _p, uses, blk0 = ldfix.f3c_track(fv)
    print('== function_%s  sslot=%s' % (k, {'[%s+0x%x]' % (b, d): n for (b, d), n in sslot.items()}))
    print('   deref=%s' % [('%x' % u[1], 'arg%d' % u[2], u[3], u[1] in blk0) for u in uses if u[0] == 'deref'])
