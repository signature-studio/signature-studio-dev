#!/usr/bin/env python3
"""disasm.py <pe> <va-hex> <size> — capstone Intel disasm of PE x64 (VA 指定)"""
import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
va = int(sys.argv[2], 16); size = int(sys.argv[3])
code = pe.get_data(va - base, size)
md = Cs(CS_ARCH_X86, CS_MODE_64)
for i in md.disasm(code, va):
    print("%x: %-8s %s" % (i.address, i.mnemonic, i.op_str))
