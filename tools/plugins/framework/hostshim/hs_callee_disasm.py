#!/usr/bin/env python3
"""hs_callee_disasm.py — FLE TFruityHost.Dispatcher の外部 callee を機械語で逆アセンブルする (#1222 / PLG-P0b-3)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<capstone,pefile> python3 hs_callee_disasm.py [N行] VA...
依存: capstone, pefile (uv pip install --target <dir> capstone pefile)。
"""
import os, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

FL = os.environ['FL_WIN64_DIR']
data = open(os.path.join(FL, 'extracted', 'block00031_PE.bin'), 'rb').read()
pe = pefile.PE(data=data)
base = pe.OPTIONAL_HEADER.ImageBase

def read_va(va, n):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = rva - s.VirtualAddress
            raw = s.get_data()
            return raw[off:off + n]
    return b''

md = Cs(CS_ARCH_X86, CS_MODE_64)
n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
for a in sys.argv[2:]:
    va = int(a, 0)
    print('== %s' % hex(va))
    code = read_va(va, n * 15)
    if not code:
        print('  WARN: VA が block00031 の section 範囲外 (出力なし)')
        continue
    for i, ins in enumerate(md.disasm(code, va)):
        print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
        if i >= n - 1:
            break
