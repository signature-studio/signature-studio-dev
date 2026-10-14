#!/usr/bin/env python3
"""SR-34: .text 内の間接 call (call [reg+disp]) と、vtable VA を rip 相対で指す lea を列挙する。
usage: indirect_calls.py <pe> <vtable_va_hex> <disp_hex> [...]
"""
import bisect
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
IMG = pe.OPTIONAL_HEADER.ImageBase
vtables = {int(sys.argv[2], 16)}
disps = {int(a, 16) for a in sys.argv[3:]}
data = open(sys.argv[1], "rb").read()


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_base = IMG + text.VirtualAddress
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]


def func_of(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = False
code = text.get_data()
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem_re = re.compile(r"^qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]$")

lea_hits = []
calls = []
for ins in md.disasm(code, t_base):
    m = rip_re.search(ins.op_str)
    if m:
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        tgt = ins.address + ins.size + d
        if tgt in vtables:
            lea_hits.append((ins.address, func_of(ins.address), ins.mnemonic, ins.op_str))
    c = mem_re.search(ins.op_str.strip()) if ins.mnemonic == "call" else None
    if c:
        disp = int(c.group(2), 16) if c.group(2) else 0
        if disp in disps:
            calls.append((ins.address, func_of(ins.address), c.group(1), disp))

print("== vtable refs (rip-relative) ==")
for a, f, mn, op in lea_hits:
    fs = f"{f:#x}" if f else "None"
    print(f"{a:#x} in {fs}  {mn} {op}")
print("== indirect calls ==")
for a, f, reg, disp in calls:
    fs = f"{f:#x}" if f else "None"
    print(f"{a:#x} in {fs}  call [{reg}+{disp:#x}]")
print("count", len(calls))
