#!/usr/bin/env python3
"""xrq.py — hc_xrefs.pkl (rip/iat xref cache) による高速 xref 照会。
usage: xrq.py VA[,VA...] [--calls-only]"""
import sys, pickle, struct
import pefile
d = pickle.load(open('/home/ubuntu/work/webstudio/tools/targets/kilohearts/license/work/hc_xrefs.pkl', 'rb'))
rip = d['rip']
import capstone
from pe_dis import pe, data, BASE, rd
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for va in [int(x, 16) for x in sys.argv[1].split(',')]:
    lst = rip.get(va, [])
    print('== %x : %d rip xrefs ==' % (va, len(lst)))
    calls, data = [], []
    for (site, fn) in lst:
        ins = next(md.disasm(rd(site - 8, 8), site - 8, 1), None)
        # 命令境界を正確に取るため 1 バイトずつ試す
        ok = None
        for back in range(1, 8):
            i2 = next(md.disasm(rd(site - back, back), site - back, 1), None)
            if i2 is not None and i2.size == back and i2.address + i2.size == site:
                ok = i2
                break
        if ok is None:
            data.append((site, fn, '?'))
            continue
        if ok.mnemonic == 'call':
            calls.append((site, fn))
        else:
            data.append((site, fn, '%s %s' % (ok.mnemonic, ok.op_str)))
    print('  calls(%d): %s' % (len(calls), ' '.join('%x(@%x)' % (f, s) for s, f in calls[:70])))
    print('  data(%d):' % len(data))
    for s, f, m in data[:70]:
        print('    %x fn=%x: %s' % (s, f, m))
