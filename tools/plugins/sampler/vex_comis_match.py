#!/usr/bin/env python3
"""VEX comis/ucomis の機械語の出現 (VA) と IR の呼び出し (!insn.addr) を 1:1 で照合する ([PLG-F3-40] #4155)。
usage: vex_comis_match.py <PE.bin> <ranges.txt> <work_dir>   (work_dir: engine_lift.sh の出力先。e.drc.ll / e.drc.c / e.final.ll を読む)
出力: 機械語側の各 VEX comis の所属関数・直後の消費命令、IR 側に呼び出しが有るか、IR のみの呼び出し。
      欠落 (機械語のみ) は、所属関数の C 出力 (e.drc.c) に当該 VA のラベルが有るかを併記する (RetDec の段で落ちたかの切り分け)。
"""
import re, sys, subprocess, os

pe_path, rng_path, work = sys.argv[1], sys.argv[2], sys.argv[3]
here = os.path.dirname(os.path.abspath(__file__))
ll = open(os.path.join(work, 'e.drc.ll')).read()
c_src = open(os.path.join(work, 'e.drc.c')).read()
meta = dict(re.findall(r'^!(\d+) = !\{i64 (\d+)\}', ll, re.M))

ir = {}
for m in re.finditer(r'call void @__asm_(v?u?comis[sd])\(.*?!insn\.addr !(\d+)', ll):
    ir.setdefault(int(meta[m.group(2)]), m.group(1))

out = subprocess.run([sys.executable, os.path.join(here, 'vex_comis_consumers.py'), pe_path, rng_path, 'v'],
                     capture_output=True, text=True, check=True).stdout
mc = {}
for line in out.splitlines():
    p = line.split()
    if len(p) >= 4 and p[1].startswith(('vcomis', 'vucomis')):
        mc[int(p[0], 16)] = (p[1], p[-1])

rng = [tuple(int(x, 16) for x in r.split('-')) for r in open(rng_path).read().strip().split(',')]


def owner(va):
    for a, b in rng:
        if a <= va <= b:
            return a
    return None


print('machine %d  IR %d' % (len(mc), len(ir)))
miss = 0
for a in sorted(mc):
    op, cons = mc[a]
    f = owner(a)
    if a in ir:
        st = 'IR:' + ir[a]
    else:
        miss += 1
        fn = ('0x%x' % f) if f is not None else '-'
        st = 'IR MISSING (fn %s, VA in e.drc.c: %s)' % (fn, 'yes' if ('// 0x%x' % a) in c_src else 'no')
    print('%x %s -> %s | %s' % (a, op, cons, st))
print('IR only: %d' % len([v for v in ir if v not in mc]))
print('missing in IR: %d' % miss)
