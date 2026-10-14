#!/usr/bin/env python3
"""hs_callee_disasm.py — FLE TFruityHost.Dispatcher の外部 callee を機械語で逆アセンブルする (#1222 / PLG-P0b-3)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<capstone,pefile> python3 hs_callee_disasm.py [N行] VA...
依存: capstone, pefile (uv pip install --target <dir> capstone pefile)。
VA は .pdata (RUNTIME_FUNCTION) の関数境界内なら、その関数の先頭から逆アセンブルする
(任意 VA から読むと命令境界を外して先頭が壊れるため)。.pdata に含まれない VA は VA から読み、
関数境界が不明である旨を出す。
"""
import bisect, os, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

FL = os.environ['FL_WIN64_DIR']
data = open(os.path.join(FL, 'extracted', 'block00031_PE.bin'), 'rb').read()
pe = pefile.PE(data=data)
base = pe.OPTIONAL_HEADER.ImageBase

FUNCS = sorted((base + e.struct.BeginAddress, base + e.struct.EndAddress)
               for e in getattr(pe, 'DIRECTORY_ENTRY_EXCEPTION', []))
FUNC_STARTS = [f[0] for f in FUNCS]

def func_of(va):
    i = bisect.bisect_right(FUNC_STARTS, va) - 1
    if i >= 0 and FUNCS[i][0] <= va < FUNCS[i][1]:
        return FUNCS[i]
    return None

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
    f = func_of(va)
    start = f[0] if f else va
    if f:
        print('== %s (pdata 関数 %s-%s の先頭から)' % (hex(va), hex(f[0]), hex(f[1])))
    else:
        print('== %s (pdata 関数境界なし: VA から読む・先頭は命令境界ずれの可能性)' % hex(va))
    code = read_va(start, n * 15)
    if not code:
        print('  WARN: VA が block00031 の section 範囲外 (出力なし)')
        continue
    for i, ins in enumerate(md.disasm(code, start)):
        if f and ins.address >= f[1]:
            break
        print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
        if i >= n - 1:
            break
