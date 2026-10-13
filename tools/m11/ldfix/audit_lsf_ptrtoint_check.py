#!/usr/bin/env python3
"""audit_lsf_ptrtoint_check.py — #484 audit_lsf.py の偽陰性 (`ptrtoint ptr %argN to i64` を別名として扱わない) の影響を測る (#510 §5.3)。
audit_lsf.py を無改変のまま読み込み、ソースの別名集合に 'ptrtoint' を足したコピーを exec して全数監査を再実行し、SUSPECT を表示する。
使い方: python3 audit_lsf_ptrtoint_check.py IR.ll IMAGE.bin 'CONFIG_GLOB'      (期待: 12 関数 / 15 site。無改変版は 8 関数 / 11 site)"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
src = open(os.path.join(HERE, 'audit_lsf.py')).read()
old = "if op in ('trunc', 'zext'):"
assert old in src
ns = {'__name__': 'patched', '__file__': os.path.join(HERE, 'audit_lsf.py')}
exec(compile(src.replace(old, "if op in ('trunc', 'zext', 'ptrtoint'):"), 'audit_lsf_patched', 'exec'), ns)
ir, img, cfg = sys.argv[1:4]
text = open(ir, errors='replace').read()
mach = ns['ImageMachine'](img, cfg)
sus = {}
for va, _a, body in ns['ir_functions'](text):
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    ms = ns['machine_sites'](mach, va, labels)
    if not ms or not ms[0]:
        continue
    lsf, ptr, _unk = ms
    st, _ld, _lines = ns['ir_stores'](body)
    for (n, w), _m in sorted(collections.Counter((n, w) for (_a2, n, w, _t) in lsf).items()):
        ex = st[(n, w)] - ptr[(n, w)]
        if ex > 0:
            sus.setdefault('%x' % va, []).append((n, w, ex))
print('suspect_fns %d suspect_sites %d' % (len(sus), sum(e for v in sus.values() for _n, _w, e in v)))
print('SUSPECT_VAS ' + ' '.join(sorted(sus, key=lambda x: int(x, 16))))
