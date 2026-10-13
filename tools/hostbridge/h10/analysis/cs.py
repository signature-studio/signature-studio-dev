#!/usr/bin/env python3
"""cs.py <pe> <va_lo> <va_hi> — capstone で VA 範囲を逆アセンブル (Ghidra なしの粗確認用)."""
import sys, pefile, capstone
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
d = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = False
for i in md.disasm(d[lo - base:hi - base], lo):
    print(f"{i.address:08x}: {i.mnemonic} {i.op_str}")
