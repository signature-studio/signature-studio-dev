#!/usr/bin/env python3
# 読み手関数ごとに、.pdata の関数境界単位で逆アセンブルし直して直接 call/jmp・RIP 相対参照の呼び出し元を列挙する。
# 線形走査の resync を避けるため、関数単位 (begin..end) で decode する。
# usage: python3 work/dll_callers.py [PE path]
import bisect
import struct
import sys

import capstone
import pefile

PATH = sys.argv[1] if len(sys.argv) > 1 else "work/key/extracted/Native Instruments/Massive X.dll"
data = open(PATH, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
secs = {}
for s in pe.sections:
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    secs.setdefault(name, (IB + s.VirtualAddress, s.SizeOfRawData, s.PointerToRawData))
tva, tsz, toff = secs[".text"]

READERS = [int(x, 16) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else []

pdata = secs[".pdata"]
praw = data[pdata[2]: pdata[2] + pdata[1]]
funcs = []
for k in range(0, len(praw) - 11, 12):
    b, e, _ = struct.unpack_from("<III", praw, k)
    if b and e > b:
        funcs.append((IB + b, IB + e))
funcs = sorted(set(funcs))
fst = [f[0] for f in funcs]


def func_of(va):
    i = bisect.bisect_right(fst, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return funcs[i][0]
    return None


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
rset = set(READERS)
hits = {r: [] for r in READERS}
undecoded = 0
for b, e in funcs:
    if b < tva or e > tva + tsz:
        continue
    code = data[toff + (b - tva): toff + (e - tva)]
    n = 0
    for ins in md.disasm(code, b):
        n += ins.size
        if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm
            if t in rset:
                hits[t].append((ins.address, ins.mnemonic, "direct", b))
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and (op.imm & 0xFFFFFFFFFFFFFFFF) in rset:
                hits[op.imm & 0xFFFFFFFFFFFFFFFF].append((ins.address, ins.mnemonic, "imm", b))
    if n != len(code):
        undecoded += 1
print("functions", len(funcs), "partial-decode", undecoded)
for r in READERS:
    print(f"reader {r:#x}: {len(hits[r])} hits")
    for a, m, k, fb in hits[r]:
        print(f"   {a:#x} {m} {k} in func {fb:#x}")
