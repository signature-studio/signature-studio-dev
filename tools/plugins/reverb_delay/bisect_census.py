#!/usr/bin/env python3
"""engine_bisect.py が特定した「RetDec が落ちる関数」と、落ちない関数の命令 mnemonic を比べる (相関の測定。 因果の確認ではない)。
usage: bisect_census.py <block> <ranges.txt> <bisect.out>
出力: bad / good の関数数・バイト、bad 側にだけ現れる mnemonic、その mnemonic のいずれかを含む関数が bad / good に何本あるか。
"""
import collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

blk, rfile, bfile = sys.argv[1:4]
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % int(blk)), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
rs = [tuple(int(x, 16) for x in r.split('-')) for r in open(rfile).read().strip().split(',')]
bad = {tuple(int(x, 16) for x in l.strip().split('-')) for l in open(bfile) if l.startswith('0x')}
md = Cs(CS_ARCH_X86, CS_MODE_64)
per = {}
cb, cg = collections.Counter(), collections.Counter()
for r in rs:
    ms = {i.mnemonic for i in md.disasm(pe.get_data(r[0] - base, r[1] - r[0] + 1), r[0])}
    per[r] = ms
    (cb if r in bad else cg).update(ms)
good = [r for r in rs if r not in bad]
only = sorted(m for m in cb if m not in cg)
sep = [m for m in only if cb[m] >= 1]
nb = sum(any(m in per[r] for m in only) for r in bad)
ng = sum(any(m in per[r] for m in only) for r in good)
bytes_ = lambda L: sum(e - s + 1 for s, e in L)
print('bad %d funcs / %d B, good %d funcs / %d B' % (len(bad), bytes_(bad), len(good), bytes_(good)))
print('bad 側にだけ現れる mnemonic (関数数): %s' % {m: cb[m] for m in only})
print('それらのいずれかを含む関数: bad %d/%d, good %d/%d' % (nb, len(bad), ng, len(good)))
