#!/usr/bin/env python3
"""site_dump.py — audit_lsf_ssa.py の JSON から、関数ごとに「機械語 (CFG 降下) + IR 本体 + site 一覧」を 1 ファイルに書き出す (目視判定用, #510)。
使い方: python3 site_dump.py IR.ll IMAGE.bin 'CONFIG_GLOB' SSA.json OUTDIR VA[,VA...]"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf as A  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

ir, img, cfg, sj, outdir, vas = sys.argv[1:7]
text = open(ir, errors='replace').read()
mach = ImageMachine(img, cfg)
data = json.load(open(sj))['functions']
bodies = {va: body for va, _a, body in A.ir_functions(text)}
os.makedirs(outdir, exist_ok=True)
for v in vas.split(','):
    va = int(v, 16)
    body = bodies[va]
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    ins = A.descend(mach, va, labels) or []
    with open(os.path.join(outdir, '%x.txt' % va), 'w') as f:
        f.write('# function_%x\n## sites (audit_lsf_ssa.py; kind=lsf: base が argN に解決 / unk: 解決不能, prov=base の由来, alg2=宛先照合の判定)\n' % va)
        for s in data.get('%x' % va, {}).get('sites', []):
            f.write('- %s kind=%s w=%d prov=%s base=%s frame=%s alg2=%s cand=%d cand_ld=%d  %s\n' % (
                s['addr'], s['kind'], s['w'], s['prov'], s['base'], s['frame'], s['alg2'], s['cand'], s['cand_ld'], s['text']))
        f.write('## machine code (descend; %d instr)\n' % len(ins))
        for i in ins:
            f.write('%x: %s %s\n' % (i.address, i.mnemonic, i.op_str))
        f.write('## IR\n' + body + '\n')
