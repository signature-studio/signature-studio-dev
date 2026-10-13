#!/usr/bin/env python3
"""PE の仮想アドレス範囲を逆アセンブルして 1 行ずつ出す (REPORT_ENGINE_LINK.md の再現用)。
usage: disasm_range.py <PE.bin> <start_va_hex> <end_va_hex>
"""
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
start, end = int(sys.argv[2], 16), int(sys.argv[3], 16)
for s in pe.sections:
    lo = base + s.VirtualAddress
    if lo <= start < lo + s.Misc_VirtualSize:
        data = s.get_data()[start - lo:end - lo]
        break
else:
    sys.exit('範囲が PE のセクションに無い')
for i in Cs(CS_ARCH_X86, CS_MODE_64).disasm(data, start):
    print(f'{i.address:#x}: {i.mnemonic} {i.op_str}')
