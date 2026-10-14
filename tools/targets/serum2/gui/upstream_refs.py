#!/usr/bin/env python3
"""SR-32 #2054: 対象 VA の参照元を .text (call rel32 / rip 相対) と .rdata (8 byte 絶対参照) から列挙する。
usage: upstream_refs.py <pe> <target_va_hex> [...]"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
targets = [int(a, 16) for a in sys.argv[2:]]
tset = set(targets)

sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
rdata = sec[b".rdata"]
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        continue
    funcs.append((IMG + b, IMG + e))
funcs.sort()


def owner(va):
    lo, hi = 0, len(funcs)
    while lo < hi:
        m = (lo + hi) // 2
        if funcs[m][0] <= va:
            lo = m + 1
        else:
            hi = m
    if lo == 0:
        return None
    b, e = funcs[lo - 1]
    return b if va < e else None


def off_of(va):
    return pe.get_offset_from_rva(va - IMG)


rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
cs = Cs(CS_ARCH_X86, CS_MODE_64)
base = IMG + text.VirtualAddress
body = text.get_data()
print("== .text: direct call / rip-relative refs ==")
for ins in cs.disasm(body, base):
    if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
        t = int(ins.op_str, 16)
        if t in tset:
            ow = owner(ins.address)
            print(f"  CALL {ins.address:#x} -> {t:#x}  in {ow:#x}" if ow else f"  CALL {ins.address:#x} -> {t:#x}")
        continue
    m = rip_re.search(ins.op_str)
    if not m:
        continue
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    tgt = ins.address + ins.size + d
    if tgt in tset:
        ow = owner(ins.address)
        print(f"  {ins.mnemonic} {ins.address:#x} -> {tgt:#x}  in {ow:#x}  [{ins.op_str}]" if ow else f"  {ins.mnemonic} {ins.address:#x} -> {tgt:#x} [{ins.op_str}]")

print("== 8 byte 絶対参照 (.rdata / .data) ==")
for name in (b".rdata", b".data"):
    s = sec[name]
    raw = data[s.PointerToRawData:s.PointerToRawData + min(s.SizeOfRawData, s.Misc_VirtualSize)]
    sbase = IMG + s.VirtualAddress
    for i in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, i)[0]
        if v in tset:
            print(f"  {name.decode()} {sbase + i:#x} = {v:#x}")
