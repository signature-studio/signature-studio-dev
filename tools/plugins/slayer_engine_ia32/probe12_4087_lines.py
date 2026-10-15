#!/usr/bin/env python3
"""probe12_4087_lines.py: probe12_4087.py の後に実行する。 異常終了した関数について、1 行ずつ native と wasm を実行し、
落ちる行 (入力) を特定する。 wasm の異常終了は node の例外メッセージを残す。 出力: work/probe12_4087/lines_<name>.txt。"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work', 'probe12_4087')
NAMES = sys.argv[1:] or ['fn_10003fe0', 'fn_100051f0', 'fn_100085a0', 'fn_100096d0', 'fn_1000a95a', 'fn_1000ba05']
img_p = os.path.join(WORK, 'image.bin')
nat = os.path.join(WORK, 'native_x87')
mjs = os.path.join(WORK, 'wasm_x87.cjs')
for name in NAMES:
    lines = [ln for ln in open(os.path.join(WORK, name + '.scen')).read().splitlines() if ln.strip()]
    res = []
    for i, ln in enumerate(lines):
        sp = os.path.join(WORK, 'one.scen')
        open(sp, 'w').write(ln + '\n')
        no = os.path.join(WORK, 'one.native')
        wo = os.path.join(WORK, 'one.wasm')
        for p in (no, wo):
            if os.path.exists(p):
                os.remove(p)
        nr = subprocess.run([nat, img_p, sp, no], capture_output=True, text=True, timeout=60).returncode
        wr = subprocess.run(['node', '--liftoff-only', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, img_p, sp, wo],
                            capture_output=True, text=True, timeout=120)
        werr = ''
        if wr.returncode:
            err = [x for x in (wr.stderr or '').splitlines() if 'Error' in x or 'RuntimeError' in x]
            werr = (err[0] if err else (wr.stderr.strip().splitlines() or [''])[-1])[:120]
        res.append('row %02d native_rc %d wasm_rc %d %s' % (i, nr, wr.returncode, werr))
    out = os.path.join(WORK, 'lines_%s.txt' % name)
    open(out, 'w').write('\n'.join(res) + '\n')
    print(name)
    print('\n'.join(res))
