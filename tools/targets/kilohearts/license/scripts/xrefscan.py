#!/usr/bin/env python3
"""xrefscan.py — 指定 VA 群への (a) 直接 call (b) rip相対データ参照 (関数ポインタ/vtable 格納) を全 .text 走査で列挙。
usage: xrefscan.py VA[,VA...] [--json OUT]  """
import sys, struct, collections
import pefile, capstone
from pe_dis import pe, data, BASE, rd

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
t = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
T_LO, T_HI = BASE + t.VirtualAddress, BASE + t.VirtualAddress + t.Misc_VirtualSize
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
_pdb = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
PDATA = []
for i in range(0, len(_pdb) // 12 * 12, 12):
    b, e, u = struct.unpack_from('<III', _pdb, i)
    if b:
        PDATA.append((BASE + b, BASE + e))
FNLO = sorted(PDATA)

targets = {int(x, 16) for x in sys.argv[1].split(',')}
outjson = None
if '--json' in sys.argv:
    outjson = sys.argv[sys.argv.index('--json') + 1]

import bisect
def fnof(a):
    i = bisect.bisect_right([x[0] for x in FNLO], a) - 1
    if i >= 0 and FNLO[i][0] <= a < FNLO[i][1]:
        return FNLO[i][0]
    return None

calls = collections.defaultdict(list)
datarefs = collections.defaultdict(list)
for (lo, hi) in PDATA:
    if not (T_LO <= lo < T_HI):
        continue
    a = lo
    while a < hi:
        ins = next(md.disasm(rd(a, 16), a, 1), None)
        if ins is None:
            break
        nxt = a + ins.size
        if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            tg = int(ins.op_str, 16)
            if tg in targets:
                calls[tg].append(a)
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = nxt + op.mem.disp
                if tgt in targets:
                    datarefs[tgt].append(a)
        a = nxt

for tg in sorted(targets):
    print('== %x ==' % tg)
    print('  direct calls (%d): %s' % (len(calls[tg]), ' '.join('%x' % x for x in calls[tg][:60])))
    fns = sorted({fnof(a) for a in calls[tg]} - {None})
    print('  caller fns (%d): %s' % (len(fns), ' '.join('%x' % x for x in fns[:80])))
    print('  data refs (%d): %s' % (len(datarefs[tg]), ' '.join('%x' % x for x in datarefs[tg][:60])))
    dfns = sorted({fnof(a) for a in datarefs[tg]} - {None})
    print('  data ref fns (%d): %s' % (len(dfns), ' '.join('%x' % x for x in dfns[:80])))
if outjson:
    import json
    json.dump({'%x' % tg: {'calls': ['%x' % x for x in calls[tg]], 'data': ['%x' % x for x in datarefs[tg]]} for tg in targets},
              open(outjson, 'w'), indent=1)
