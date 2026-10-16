#!/usr/bin/env python3
"""PY-5352 (#5493): 群 D の受け手 global [rip+0xae51a1] (0xbd1bd8 → 0x80d9c0) の出所を辿る (実機不要・近似)。

  python3 analysis/py5493_global.py <PE.bin> [global VA hex] [table VA hex]

1 回の線形走査で次を集める (既定値は #5493 の測定値):
1. global を RIP 相対で指す命令 (読み・書き)。
2. global の VA を値として持つ .data のポインタ表 (table) を RIP 相対で指す命令。
3. 0x80d9c0・0x80d9d0・0x80dcc0 への直接 call。
"""
import sys

import capstone
import pefile

path = sys.argv[1]
G = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x16B6D80
TBL = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x15DFD18
FNS = {0x80D9C0, 0x80D9D0, 0x80DCC0}

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = ib + text.VirtualAddress

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
rip_g, rip_tbl, calls = [], [], []
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            if tgt == G:
                rip_g.append((ins.address, ins.mnemonic, ins.op_str))
            elif tgt == TBL:
                rip_tbl.append((ins.address, ins.mnemonic, ins.op_str))
    if ins.mnemonic == "call" and ins.operands[0].type == capstone.x86.X86_OP_IMM:
        if ins.operands[0].imm in FNS:
            calls.append((ins.address, ins.operands[0].imm))

for a, m, o in rip_g:
    print(f"global {G:#x} <- {a:#x}: {m} {o}")
for a, m, o in rip_tbl:
    print(f"table  {TBL:#x} <- {a:#x}: {m} {o}")
for a, f in calls:
    print(f"call {f:#x} at {a:#x}")
