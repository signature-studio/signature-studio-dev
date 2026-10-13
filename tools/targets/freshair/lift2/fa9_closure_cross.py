#!/usr/bin/env python3
"""fa9_closure_cross.py <SlateCore.core_64> — FA-9 §12-2: process / ctor 閉包 (closure.py, --stop 無し) と
即値 ID 候補関数 (fa9_imm_scan.py の列挙, 53 件) の交差を数える。交差 0 = 候補は閉包の外。"""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); FA = os.path.dirname(HERE)
core = sys.argv[1]
ROOTS = [('process Compressor', '0x180775220'), ('process Filter', '0x180b6f050'), ('process Gain', '0x180afe090'),
         ('ctor Compressor', '0x180774cd0'), ('ctor Filter', '0x180b6ed50'), ('ctor Gain', '0x180afde00')]
imm = set()
for ln in subprocess.run([sys.executable, os.path.join(HERE, 'fa9_imm_scan.py'), core], capture_output=True, text=True, check=True).stdout.splitlines():
    m = re.match(r'^(0x[0-9a-f]+) +\d+ ', ln)
    if m: imm.add(int(m.group(1), 16))
print('即値候補関数: %d' % len(imm))
with tempfile.TemporaryDirectory() as td:
    for name, root in ROOTS:
        j = os.path.join(td, 'c.json')
        subprocess.run([sys.executable, os.path.join(FA, 'closure.py'), core, root, '--json', j], capture_output=True, check=True)
        fs = {int(f['va'], 16) for f in json.load(open(j))['funcs']}
        print('%-18s root %s: 閉包 %d 関数, 候補との交差 %d' % (name, root, len(fs), len(fs & imm)))
