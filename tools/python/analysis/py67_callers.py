#!/usr/bin/env python3
"""PY-67 (#2159): 指定した関数への direct call の呼出し元と直前 8 命令を出す (実機不要)。

  python3 analysis/py67_callers.py <PE.bin> <callee VA hex>[,<callee VA hex>...]

.text を 1 回線形走査する (py67_slot.py と同じ走査)。呼出し元の前後関係を見て、
引数レジスタ (rcx/rdx/r8/r9) に入る値の由来を判断する。
"""
import sys

import capstone
import pefile

path = sys.argv[1]
targets = {int(v, 0) for v in sys.argv[2].split(",")}

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff = text.PointerToRawData
tsize = text.SizeOfRawData
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
tdata = data[toff:toff + tsize]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X = capstone.x86

prev = []
n = 0
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X.X86_OP_IMM and ins.operands[0].imm in targets:
        n += 1
        print(f"call {ins.operands[0].imm:#x} at {ins.address:#x}")
        print("    before: " + " | ".join(f"{a:#x}: {m} {o}" for a, m, o in prev[-8:]))
    prev.append((ins.address, ins.mnemonic, ins.op_str))
    if len(prev) > 8:
        prev.pop(0)
print(f"# direct calls: {n}")
