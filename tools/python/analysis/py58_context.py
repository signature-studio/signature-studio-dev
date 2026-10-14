#!/usr/bin/env python3
"""PY-58 (#1973): 指定 VA の前後を逆アセンブルし、書込み命令に <== を付けて出す (実機不要)。

  python3 analysis/py58_context.py <PE.bin> <VA hex,VA hex,...> [before_bytes] [after_bytes]

before / after は 10 進または 0x 付き 16 進。
"""
import sys

import capstone
import pefile

path = sys.argv[1]
vas = [int(v, 0) for v in sys.argv[2].split(",")]
before = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x180
after = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x40

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
data = open(path, "rb").read()
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = base + text.VirtualAddress
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

for va in vas:
    start = va - before
    off = start - tbase
    chunk = tdata[off:off + before + after]
    print(f"===== around {va:#x} =====")
    for ins in md.disasm(chunk, start):
        mark = " <==" if ins.address == va else ""
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}{mark}")
    print()
