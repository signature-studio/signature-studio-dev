#!/usr/bin/env python3
"""f1088.py — EditorModel sub-object (+0x1088 編集可否 flag) の読み/書き箇所を全 .text 走査で列挙する。

方法: .pdata の 111,666 関数範囲を線形逆アセンブルし、mem オペランドの disp == 0x1088
(base は rip 以外) の命令を収集する。RIP 相対 (disp がアドレス) は除外。
usage: f1088.py [--json OUT.json]   (関数別 読み/書き/命令一覧)
"""
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

OFF = 0x1088
res = {}  # fn -> list of (addr, mnem, op, is_write, width)
for (lo, hi) in PDATA:
    if not (T_LO <= lo < T_HI):
        continue
    a = lo
    while a < hi:
        ins = next(md.disasm(rd(a, 16), a, 1), None)
        if ins is None:
            break
        nxt = a + ins.size
        if 'rip' in ins.op_str:
            a = nxt
            continue
        # mem operand の disp を capstone から取る
        disp = None
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM:
                m = op.mem
                if m.base != capstone.x86.X86_REG_RIP and m.disp == OFF:
                    disp = (m.base, m.index, ins.op_str)
        if disp is not None:
            isw = False
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.access & capstone.CS_AC_WRITE:
                    isw = True
            res.setdefault(lo, []).append((a, ins.mnemonic, ins.op_str, isw, ins.size))
        a = nxt

wr = {f: v for f, v in res.items() if any(x[3] for x in v)}
rdonly = {f: v for f, v in res.items() if f not in wr}
print('functions touching +0x1088: total %d, with WRITE %d, read-only %d' % (len(res), len(wr), len(rdonly)))
for f, v in sorted(wr.items()):
    sz = next((h - f for (l, h) in PDATA if l == f), 0)
    print('WRITE %x size=%d:' % (f, sz))
    for (a, mn, ops, isw, szn) in v:
        print('   %x: %s %s' % (a, mn, ops))
import json
out = {'write': {'%x' % f: [['%x' % a, mn, ops, isw] for (a, mn, ops, isw, _) in v] for f, v in wr.items()},
       'read': {'%x' % f: [['%x' % a, mn, ops, isw] for (a, mn, ops, isw, _) in v] for f, v in rdonly.items()}}
if '--json' in sys.argv:
    json.dump(out, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
