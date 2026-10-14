#!/usr/bin/env python3
"""SR-32 #2054: VA 範囲を逆アセンブルし、所属関数 (.pdata) を見出しに出す。
usage: disasm_range.py <pe> <start_hex> <end_hex>"""
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
start, end = int(sys.argv[2], 16), int(sys.argv[3], 16)
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.append((IMG + b, IMG + e))
text = sec[b".text"]
tbase = IMG + text.VirtualAddress
raw = text.get_data()
cs = Cs(CS_ARCH_X86, CS_MODE_64)
seg = raw[start - tbase:end - tbase]
owner = [f for f in funcs if f[0] <= start < f[1]]
print(f"# range {start:#x}-{end:#x} owner={[hex(o[0]) for o in owner]} size={[o[1]-o[0] for o in owner]}")
for ins in cs.disasm(seg, start):
    print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
