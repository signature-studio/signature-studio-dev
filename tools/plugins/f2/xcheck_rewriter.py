#!/usr/bin/env python3
"""PLG-F2 (#514) 別算法検算: icall_gate.py の機械語側 (capstone 線形 sweep) と、icall_rewrite.py が閉包を recursive descent で走査して
dispatch 化した site (work/batch/<block>/p.icall.map.json の sites のうち mn=call) の VA 集合を突合する。 集合一致なら EQ。
  cd tools/plugins && python3 f2/xcheck_rewriter.py <block> ...
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from icall_gate import machine_sites, parse_ranges, W, FL_WIN64_DIR
tot = [0, 0]
bad = 0
for b in map(int, sys.argv[1:]):
    calls, _ = machine_sites(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b),
                             parse_ranges(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)))
    m = json.load(open(os.path.join(W, 'batch', str(b), 'p.icall.map.json')))
    rw = {s['va'] for s in m['sites'] if s['mn'] == 'call'}
    ok = rw == set(calls)
    bad += not ok
    tot[0] += len(calls); tot[1] += len(rw)
    print('%d linear-sweep=%d rewriter(call)=%d only_sweep=%d only_rewriter=%d %s' % (
        b, len(calls), len(rw), len(set(calls) - rw), len(rw - set(calls)), 'EQ' if ok else 'DIFF'))
print('合計 linear-sweep=%d rewriter(call)=%d' % tuple(tot))
sys.exit(1 if bad else 0)
