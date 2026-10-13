#!/usr/bin/env python3
"""vex256_census.py — 難 4 本 (Convolver / Filter Table / Ladder / Slice EQ) の snap-in 固有 closure
(closures_sets.pkl の unique) に現れる ymm 命令と VEX 系 FMA を mnemonic 単位で列挙する (読取専用)。

入力 (work/, gitignore): closures_sets.pkl (scripts/closures.py の出力) / callgraph.pkl (scripts/callgraph.py)
  + HeartCore.core_64 (work/winpkg)。closure の集計は scripts/closures.py と同じ unique 定義。
usage (tools/targets/kilohearts から): python3 snapins/scripts/vex256_census.py [--json OUT]
数え方: unique closure の各関数を capstone で全命令走査し、(a) オペランドに ymm を含む命令、
  または (b) mnemonic が v で始まる命令 (VEX 符号化、xmm 形 vblend*/vperm* を含む) を 1 件と数える (同一 VA の再計数はしない)。
"""
import collections, json, os, pickle, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone
from pe_dis import rd, BASE

KH = os.path.abspath(os.path.join(HERE, '..', '..'))
NS = ['convolver', 'filtertable', 'ladder', 'equalizer']
S = pickle.load(open(os.path.join(KH, 'work', 'closures_sets.pkl'), 'rb'))
RES = pickle.load(open(os.path.join(KH, 'work', 'callgraph.pkl'), 'rb'))['res']
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

per = collections.defaultdict(collections.Counter)
example = {}
ymm_total = collections.Counter()
for ns in NS:
    for f in S['sets'][ns]:
        if f not in RES:
            continue
        code = rd(BASE + f, RES[f]['size'])
        for i in md.disasm(code, BASE + f):
            is_ymm = 'ymm' in i.op_str
            if is_ymm:
                ymm_total[ns] += 1
            if is_ymm or i.mnemonic.startswith('v'):
                per[i.mnemonic][ns] += 1
                example.setdefault(i.mnemonic, '%x %s %s' % (i.address, i.mnemonic, i.op_str))

out = {m: {'per_snapin': dict(per[m]), 'total': sum(per[m].values()), 'example': example[m]} for m in sorted(per)}
for m, v in out.items():
    print('%-12s %s total=%d | %s' % (m, v['per_snapin'], v['total'], v['example']))
print('ymm-operand instructions per snap-in:', dict(ymm_total))
if len(sys.argv) > 2 and sys.argv[1] == '--json':
    json.dump(out, open(sys.argv[2], 'w'), indent=1)
