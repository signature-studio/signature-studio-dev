#!/usr/bin/env python3
"""PE x64 の VA 範囲を逆アセンブルする小道具。 pedis.py <PE> <VA> [bytes=256] [--until-ret]"""
import sys, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

def main():
    path = sys.argv[1]
    va = int(sys.argv[2], 16)
    n = int(sys.argv[3], 0) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 256
    until = '--until-ret' in sys.argv
    d = open(path, 'rb').read()
    pe = pefile.PE(data=d)
    base = pe.OPTIONAL_HEADER.ImageBase
    o = pe.get_offset_from_rva(va - base)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    for i in md.disasm(d[o:o + n], va):
        print('%x: %-8s %s' % (i.address, i.mnemonic, i.op_str))
        if until and i.mnemonic in ('ret', 'int3') and i.address - va > 8:
            break

if __name__ == '__main__':
    main()
