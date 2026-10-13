#!/usr/bin/env python3
"""fa8_imm.py <pe> <imm-hex>... — .pdata 全関数から、指定即値 (0x157 等) を持つ命令を含む関数を列挙する (静的)。"""
import sys, struct, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
want = set(int(x, 16) for x in sys.argv[2:])
dd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]; raw = pe.get_data(dd.VirtualAddress, dd.Size)
fn = sorted(struct.unpack_from('<III', raw, i)[:2] for i in range(0, len(raw) - 11, 12))
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
hits = {}
for b, e in fn:
    if e <= b: continue
    for i in md.disasm(pe.get_data(b, e - b), base + b):
        if i.mnemonic in ('call', 'jmp') or i.mnemonic.startswith('j'): continue
        for op in i.operands:
            if op.type == X86_OP_IMM and (op.imm & 0xffffffff) in want:
                hits.setdefault(base + b, []).append('%x:%s %s' % (i.address, i.mnemonic, i.op_str))
for f, l in hits.items(): print('func %x (%d hits): %s' % (f, len(l), ' ; '.join(l[:3])))
print('funcs=%d with-imm=%d' % (len(fn), len(hits)))
