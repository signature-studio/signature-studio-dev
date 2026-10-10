#!/usr/bin/env python3
"""dis_annot.py <pe> <va-hex> <size> — capstone disasm + RIP 相対定数 (f32/f64/u32/u64/16B) 注釈"""
import sys, struct, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
va = int(sys.argv[2], 16); size = int(sys.argv[3])
code = pe.get_data(va - base, size)
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
for i in md.disasm(code, va):
    note = ''
    for op in i.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            t = i.address + i.size + op.mem.disp
            try:
                b = pe.get_data(t - base, 16)
                f = struct.unpack('<f', b[:4])[0]; d = struct.unpack('<d', b[:8])[0]
                note = '  ; [%x] u32=%08x f32=%g f64=%g | %s' % (t, struct.unpack('<I', b[:4])[0], f, d, b.hex())
            except Exception as e:
                note = '  ; [%x] ?' % t
    print("%x: %-8s %s%s" % (i.address, i.mnemonic, i.op_str, note))
