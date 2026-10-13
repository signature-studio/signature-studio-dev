#!/usr/bin/env python3
# MX-3b U1: 指定 VA から最大 N 命令を逆アセンブルし、第 2 引数 (rdx = ProcessData*) の
# 参照 offset を集計する。ret / int3 の直後の境界は見ない (pdata 非依存)。
# usage: mx_slot_body.py <pe> <func_va_hex> [max_insn]
import sys, re, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, fva = sys.argv[1], int(sys.argv[2], 16)
maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 400
pe = pefile.PE(pe_path, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
code = None
for s in pe.sections:
    base = IB + s.VirtualAddress
    if base <= fva < base + s.Misc_VirtualSize:
        off = fva - IB
        code = data[off:off + 0x2000]
        break
assert code is not None, 'VA not in a section'

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
offs = collections.Counter()
calls = []
n = 0
for ins in md.disasm(code, fva):
    n += 1
    if n > maxn:
        break
    if ins.mnemonic == 'call':
        calls.append((ins.address, ins.op_str))
    for op in ins.operands:
        if op.type == 3 and op.mem.base != 0:  # MEM
            if md.reg_name(op.mem.base) == 'rdx':
                offs[op.mem.disp] += 1
    if ins.mnemonic == 'ret' and n > 30:
        break
print('insns=%d' % n)
print('rdx-based mem offsets:', sorted(offs.items()))
print('calls: %d' % len(calls))
for a, o in calls[:40]:
    print('  %x call %s' % (a, o))
