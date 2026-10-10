#!/usr/bin/env python3
"""pe_dis.py — HeartCore.core_64 の VA 範囲を capstone で逆アセンブル (読取専用ユーティリティ)。
usage: pe_dis.py <VA> [size|auto]   (auto: callgraph.pkl の size を使う)"""
import sys, struct, pefile, capstone
P = '/home/ubuntu/work/webstudio/tools/targets/kilohearts/work/winpkg/HeartCore.core_64'
pe = pefile.PE(P, fast_load=True)
data = open(P, 'rb').read()
BASE = pe.OPTIONAL_HEADER.ImageBase
def rd(va, n):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            o = s.PointerToRawData + rva - s.VirtualAddress
            return data[o:o+n]
    raise ValueError(hex(va))
if __name__ == '__main__':
    va = int(sys.argv[1], 16)
    n = int(sys.argv[2], 0) if len(sys.argv) > 2 else 64
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i in md.disasm(rd(va, n), va):
        print('%x:\t%s\t%s' % (i.address, i.mnemonic, i.op_str))
