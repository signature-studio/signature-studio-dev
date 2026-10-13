#!/usr/bin/env python3
"""use_residual_509.py — #509: audit_lsf.py の消費者形 (SUSPECT_USE, pure) が修復後に残った理由を ldfix.fix_f3c_use の門ごとに分類する。
使い方: python3 use_residual_509.py IR.ll IMAGE.bin 'CONFIG_GLOB' AUDIT.json   (AUDIT.json = audit_lsf.py --json の出力。IR.ll は同じ IR)
分類: first-deref-not-entry (最初の deref が entry ブロック外) / ptr-arg (引数が ptr 型) / w32 (32bit deref を含む) /
      raw-after (最初の deref より後に生の使用を ldfix が検出) / tracker-no-deref (audit は deref を見るが ldfix の記号実行は見ない) / none (どの門にも掛からない)"""
import collections
import json
import re
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

ir, image, cfg, aj = sys.argv[1:5]
text = open(ir, errors='replace').read()
mach = ImageMachine(image, cfg)
for x in ldfix.DEF_RE.finditer(text):
    ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
sus = json.load(open(aj))['suspects_use']
cnt = collections.Counter()
rows = []
for k, v in sus.items():
    va = int(k, 16)
    body = re.search(r'^define [^\n]*@function_%s\(.*?\n}\n' % k, text, re.M | re.S).group(0)
    hdr = re.match(r'define [^@]*@function_\w+\(([^)]*)\)', body).group(1).split(',')
    labs = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    mach.cover(va, max(labs))
    _lsf, _ptr, uses, blk0 = ldfix.f3c_track(FnMach(mach, va, labs))
    for e in v:
        n = e['arg']
        ds = [u for u in uses if u[0] == 'deref' and u[2] == n]
        why = []
        if not ds:
            why.append('tracker-no-deref')
        else:
            first = min(u[1] for u in ds)
            if first not in blk0:
                why.append('first-deref-not-entry')
            if hdr[n - 1].split()[0] != 'i64':
                why.append('ptr-arg')
            if not all(u[3] == 64 for u in ds):
                why.append('w32')
            if any(u[0] == 'raw' and u[2] == n and u[1] > first for u in uses):
                why.append('raw-after')
        why = '+'.join(why) or 'none'
        cnt[why] += 1
        rows.append((k, n, why))
for w, c in cnt.most_common():
    print('%3d  %s' % (c, w))
print('合計 %d (関数, 引数) / %d 関数' % (sum(cnt.values()), len(sus)))
if len(sys.argv) > 5:
    for r in rows:
        print('  function_%s arg%d %s' % r)
