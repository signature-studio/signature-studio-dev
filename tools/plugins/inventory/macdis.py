#!/usr/bin/env python3
"""mac x86_64 スライスの VA 逆アセンブル: macdis.py <dylib> <VA hex> [bytes] [--until-ret]
(__TEXT は slice 先頭=VA 0 のフラット対応: file_off = slice_off + VA)"""
import sys, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
p = sys.argv[1]; va = int(sys.argv[2], 16)
n = int(sys.argv[3], 0) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 256
d = open(p, 'rb').read()
off = 0
if struct.unpack_from('>I', d, 0)[0] == 0xcafebabe:
    for i in range(struct.unpack_from('>I', d, 4)[0]):
        cpu, sub, o, sz, al = struct.unpack_from('>iiIII', d, 8 + 20 * i)
        if cpu == 0x01000007: off = o
md = Cs(CS_ARCH_X86, CS_MODE_64)
for i in md.disasm(d[off + va: off + va + n], va):
    print('%x: %-8s %s' % (i.address, i.mnemonic, i.op_str))
    if '--until-ret' in sys.argv and i.mnemonic == 'ret' and i.address - va > 4: break
