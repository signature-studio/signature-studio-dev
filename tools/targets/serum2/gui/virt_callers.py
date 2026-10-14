#!/usr/bin/env python3
"""SR-32 #2054: .text 内の (a) 直接 call rel32 で対象 VA を呼ぶ箇所、(b) `call qword ptr [reg+disp]` で
disp が指定値のもの、を所属関数付きで列挙する。
usage: virt_callers.py <pe> <direct_target_hex> <disp_hex>"""
import struct
import sys
from collections import Counter

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
direct = int(sys.argv[2], 16)
disp = int(sys.argv[3], 16)
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.append((IMG + b, IMG + e))
funcs.sort()


def owner(va):
    for b, e in funcs:
        if b <= va < e:
            return b
    return None


text = sec[b".text"]
cs = Cs(CS_ARCH_X86, CS_MODE_64)
virt = []
dirs = []
for ins in cs.disasm(text.get_data(), IMG + text.VirtualAddress):
    if ins.mnemonic != "call":
        continue
    op = ins.op_str
    if op.startswith("0x"):
        if int(op, 16) == direct:
            dirs.append(ins.address)
        continue
    if op.startswith("qword ptr [") and op.endswith("]"):
        inner = op[len("qword ptr ["):-1]
        parts = inner.split(" + ")
        if len(parts) == 2 and parts[1].strip().lower() == hex(disp):
            virt.append((ins.address, inner))
print(f"== direct call -> {direct:#x}: {len(dirs)} 件")
for a in dirs:
    o = owner(a)
    print(f"  {a:#x}  in {o:#x}" if o else f"  {a:#x}")
print(f"== call qword ptr [reg+{disp:#x}]: {len(virt)} 件 (所属関数の数 {len(set(owner(a) for a,_ in virt))})")
for a, inner in virt:
    o = owner(a)
    print(f"  {a:#x}  in {o:#x}  [{inner}]" if o else f"  {a:#x}  [{inner}]")
