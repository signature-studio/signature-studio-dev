#!/usr/bin/env python3
"""Fruity Delphi plugin DLL から SaveRestoreState (vtable slot 3) の VA を求めて逆アセンブルする。
usage: plugin_slot3.py <plugin_x64.dll> [--max N]
CreatePlugInstance の `mov rcx,[rip+d]` (class ref) -> [classref]=&vtable[0]? -> vtable[3]。 (tools/plugins/ABI.md §3)"""
import sys, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
path = sys.argv[1]
mx = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 400
d = open(path, 'rb').read(); pe = pefile.PE(data=d); base = pe.OPTIONAL_HEADER.ImageBase
rd = lambda va, n: d[pe.get_offset_from_rva(va - base):][:n]
q = lambda va: struct.unpack('<Q', rd(va, 8))[0]
ent = [base + e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b'CreatePlugInstance'][0]
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
cref = None
for i in md.disasm(rd(ent, 120), ent):
    if i.mnemonic == 'mov' and 'rcx, qword ptr [rip' in i.op_str and i.address > ent + 0x20:
        op = i.operands[1]; cref = i.address + i.size + op.mem.disp; break
print('classref slot VA', hex(cref))
v0 = q(cref)
print('[classref] =', hex(v0))
for k in range(0, 8):
    print('  vtable[%d] = %x' % (k, q(v0 + 8 * k)))
vt0 = q(cref)
s3 = q(vt0 + 8 * 3)
print('slot3 SaveRestoreState VA', hex(s3))
for i in md.disasm(rd(s3, 4096), s3):
    print('%x: %-7s %s' % (i.address, i.mnemonic, i.op_str))
    if i.mnemonic == 'ret' and i.address - s3 > 8 and mx <= 0: break
    mx -= 1
    if mx < -400: break
