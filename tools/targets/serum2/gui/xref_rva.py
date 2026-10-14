#!/usr/bin/env python3
"""List .text instructions whose rip-relative operand resolves to given file offsets.
usage: xref_rva.py <Serum2_win64.vst3> <file_offset_hex> [...]"""
import re
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
IMG = pe.OPTIONAL_HEADER.ImageBase
targets = {IMG + pe.get_rva_from_offset(int(a, 16)): int(a, 16) for a in sys.argv[2:]}
text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
base = IMG + text.VirtualAddress
rip_re = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
for ins in Cs(CS_ARCH_X86, CS_MODE_64).disasm(text.get_data(), base):
    m = rip_re.search(ins.op_str)
    if not m:
        continue
    d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    tgt = ins.address + ins.size + d
    if tgt in targets:
        print(f'{ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {tgt:#x} (file 0x{targets[tgt]:x})')
