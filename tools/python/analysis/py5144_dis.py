#!/usr/bin/env python3
"""PY-5144 (#5144): 指定 VA 範囲の逆アセンブル (受け手の出所確認用)。

  python3 analysis/py5144_dis.py <PE.bin> <start_va_hex> <end_va_hex>
"""
import sys

import capstone
import pefile

path, lo, hi = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tbase = ib + text.VirtualAddress
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
for ins in md.disasm(tdata[lo - tbase:hi - tbase], lo):
    print(f"{ins.address:#x}  {ins.mnemonic} {ins.op_str}")
