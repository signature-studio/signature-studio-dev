#!/usr/bin/env python3
# disasm_range_4263.py — block24350_PE.bin の VA 範囲を逆アセンブルする (T-SH-107 / #4263)。
# 使い方: python3 disasm_range_4263.py <block24350_PE.bin> <start_va_hex> <end_va_hex>
# 例: python3 disasm_range_4263.py block24350_PE.bin 0x40f4e1 0x40f4f0   (flag [0x5d0cb0] の書込み)
# 依存: pip install pefile capstone (Python 3)
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
IMG = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
data = text.get_data()
base = IMG + text.VirtualAddress
a, b = int(sys.argv[2], 16), int(sys.argv[3], 16)
md = Cs(CS_ARCH_X86, CS_MODE_64)
for i in md.disasm(data[a - base:b - base], a):
    print(f"{i.address:#x}: {i.mnemonic} {i.op_str}")
