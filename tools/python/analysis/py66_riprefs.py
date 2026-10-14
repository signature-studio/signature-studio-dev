#!/usr/bin/env python3
"""PY-66 (#2078): 指定 VA 範囲を RIP 相対メモリオペランドで指す命令を .text 内から探す (実機不要)。

  python3 analysis/py66_riprefs.py <PE.bin> <VA hex>[:<len hex>] [VA hex[:len]...]

- .text を先頭から線形走査 (capstone) し、RIP 相対メモリオペランドの参照先
  (ins.address + ins.size + disp) が指定範囲に入るものを出す。
- 線形走査は命令境界がずれることがある。出力の命令 VA は py58_context.py の逆アセンブルで
  命令境界を確かめてから採用すること。
"""
import sys

import capstone
import pefile

path = sys.argv[1]
ranges = []
for spec in sys.argv[2:]:
    va, _, ln = spec.partition(":")
    ranges.append((int(va, 0), int(ln, 0) if ln else 1))

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff = text.PointerToRawData
tsize = text.SizeOfRawData
tbase = base + text.VirtualAddress
tdata = data[toff:toff + tsize]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def hit(tgt):
    return any(lo <= tgt < lo + ln for lo, ln in ranges)


n = 0
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    n += 1
    off += ins.size
    for op in ins.operands:
        if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
            continue
        tgt = ins.address + ins.size + op.mem.disp
        if hit(tgt):
            print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {tgt:#x}")
print(f"# decoded {n} insns", file=sys.stderr)
