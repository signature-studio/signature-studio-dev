#!/usr/bin/env python3
"""PY-5144 (#5144): .text 全域で `mov [reg+disp], ...` の書込みサイトを列挙する。

  python3 analysis/py5144_writes.py <PE.bin> <disp16>

群 C の受け手 (Self のフィールド +0x18・+0x7a0) について、そのフィールドに値を
書く命令が .text にあるかを見る。reg は rip/rsp/rbp 以外の基底に限る (フレーム除外)。
線形走査 (64KiB 単位) の近似で、データ部の誤デコードを含みうる。
"""
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
disp_want = int(sys.argv[2], 16)

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tbase = ib + text.VirtualAddress
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
hits = []
pos = 0
while pos < len(tdata):
    end = min(len(tdata), pos + 0x10000)
    for ins in md.disasm(tdata[pos:end], tbase + pos):
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            continue
        d = ins.operands[0]
        if (d.type == X.X86_OP_MEM and d.mem.index == 0 and d.mem.disp == disp_want
                and d.mem.base not in (X.X86_REG_RIP, X.X86_REG_RSP, X.X86_REG_RBP, 0)):
            hits.append(ins.address)
    pos = end

print(f"mov [reg+{disp_want:#x}] 書込み {len(hits)} 件")
for h in hits:
    print(f"  {h:#x}")
