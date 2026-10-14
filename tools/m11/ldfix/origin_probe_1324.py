#!/usr/bin/env python3
"""origin_probe_1324.py — #1324: tracker-no-deref 3 組の deref の出所 ('arg' | 'argv') を表示する。
使い方 (tools/m11 で実行): python3 ldfix/origin_probe_1324.py
入力: work/boot_final3.ll・work/m11_image.bin・work/boot*.drc.config.json"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

text = open('work/boot_final3.ll', errors='replace').read()
mach = ImageMachine('work/m11_image.bin', 'work/boot*.drc.config.json')
for x in ldfix.DEF_RE.finditer(text):
    ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
for k, n in [('75a180', 4), ('db6480', 4), ('dc27c0', 2), ('5c44b0', 2)]:
    va = int(k, 16)
    body = re.search(r'^define [^\n]*@function_%s\(.*?\n}\n' % k, text, re.M | re.S).group(0)
    labs = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    mach.cover(va, max(labs))
    _lsf, _ptr, uses, _blk0 = ldfix.f3c_track(FnMach(mach, va, labs))
    print('function_%s arg%d' % (k, n))
    for u in uses:
        if u[0] in ('deref', 'raw') and u[2] == n:
            print('   ', u)
