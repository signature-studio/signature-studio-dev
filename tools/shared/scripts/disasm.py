#!/usr/bin/env python3
"""disasm.py <macho-x86_64> <startVA> <stopVA>  (capstone; llvm-objdump の --start-address が Mach-O で効かないための代替)"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from macho_util import MachO
import capstone
m = MachO(sys.argv[1]); a = int(sys.argv[2], 16); b = int(sys.argv[3], 16)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
o = m.va2off(a)
for i in md.disasm(m.d[o:o + (b - a)], a):
    print(f"{i.address:x}:\t{i.mnemonic}\t{i.op_str}")
