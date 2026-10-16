#!/usr/bin/env python3
"""SR-85 #5935: .text 全体で、rip 相対メモリ参照が指定 VA を指す命令を列挙する (読み/書きを区別)。
usage: xref_slot_writes.py <pe> <target_va_hex>"""
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
IMG = pe.OPTIONAL_HEADER.ImageBase
tgt = int(sys.argv[2], 16)
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
base = IMG + text.VirtualAddress
raw = text.get_data()
cs = Cs(CS_ARCH_X86, CS_MODE_64)
cs.detail = True
n = 0
for ins in cs.disasm(raw, base):
    for i, op in enumerate(ins.operands):
        if op.type == 3 and op.mem.base == 41 and op.mem.index == 0:  # X86_REG_RIP
            if ins.address + ins.size + op.mem.disp == tgt:
                n += 1
                kind = "WRITE" if i == 0 else "READ"
                print(f"{kind}\t0x{ins.address:x}\t{ins.mnemonic} {ins.op_str}")
print(f"total_refs={n}", file=sys.stderr)
