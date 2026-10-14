#!/usr/bin/env python3
"""gate_5c44b0_1324.py — #1324 (LD-45): 5c44b0 (none) の fix_f3c_use 門 (a)〜(d) と置換対象 rep_idx を出す。
使い方 (tools/m11 で実行): python3 ldfix/gate_5c44b0_1324.py [IR.ll] [VA...]  (既定 IR = work/boot_final3.ll)
各門の判定を ldfix.fix_f3c_use と同じ式で再計算し、置換行 (rep_idx) と entry_end を表示する。"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

ir = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else 'work/boot_final3.ll'
vas = [a for a in sys.argv[1:] if not os.path.exists(a)] or ['5c44b0']
text = open(ir, errors='replace').read()
mach = ImageMachine('work/m11_image.bin', 'work/boot*.drc.config.json')
for x in ldfix.DEF_RE.finditer(text):
    ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
for k in vas:
    va = int(k, 16)
    body = re.search(r'^define [^\n]*@function_%s\(.*?\n}\n' % k, text, re.M | re.S).group(0)
    labs = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    mach.cover(va, max(labs))
    fv = ldfix.FnMach(mach, va, labs) if hasattr(ldfix, 'FnMach') else FnMach(mach, va, labs)
    _lsf, _ptr, uses, blk0 = ldfix.f3c_track(fv)
    lines = body.split('\n')
    entry_end = next((q for q in range(2, len(lines)) if re.match(r'^[\w.$-]+:', lines[q])), len(lines))
    print('== function_%s entry_end=%d' % (k, entry_end))
    print('   uses=%s' % uses)
    for n in sorted({u[2] for u in uses}):
        derefs = [u for u in uses if u[0] == 'deref' and u[2] == n]
        raws = [u for u in uses if u[0] == 'raw' and u[2] == n]
        first = min((u[1] for u in derefs), default=None)
        argre = re.compile(r'(?<![\w.$-])%%arg%d(?![\w.$-])' % n)
        idx = [q for q in range(1, len(lines)) if argre.search(lines[q])]
        loaded = [q for q in range(1, len(lines)) if re.match(r'^\s*%[\w.$-]+ = load [^,]+, ptr %arg' + str(n) + r'\b', lines[q])]
        print('   arg%d derefs=%s raws=%d first_in_entry=%s loaded_direct=%s' % (
            n, [(hex(u[1]), u[3]) for u in derefs], len(raws), (first in blk0) if first is not None else None, loaded))
        print('   arg%d IR uses=%s keep=%d rep_idx=%s' % (n, idx, len(raws), idx[len(raws):]))
