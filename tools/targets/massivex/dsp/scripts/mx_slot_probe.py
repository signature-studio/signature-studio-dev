#!/usr/bin/env python3
# MX-3b U1: vtable slot の先頭 VA を pdata 非依存で読み、各 slot の先頭命令列を出す。
# usage: mx_slot_probe.py <pe> <vtable_va_hex> <nslots> [ninsn]
import sys, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, vt_hex, nslots = sys.argv[1], sys.argv[2], int(sys.argv[3])
ninsn = int(sys.argv[4]) if len(sys.argv) > 4 else 12
pe = pefile.PE(pe_path, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
secs = [(IB + s.VirtualAddress, s.VirtualAddress, s.Misc_VirtualSize, s) for s in pe.sections]

def read_va(va, n):
    for base, rva, vsz, s in secs:
        if base <= va < base + vsz:
            off = va - IB
            return data[off:off + n]
    return None

def sec_name(va):
    for base, rva, vsz, s in secs:
        if base <= va < base + vsz:
            return s.Name.rstrip(b'\0').decode()
    return '?'

md = Cs(CS_ARCH_X86, CS_MODE_64)
vt = int(vt_hex, 16)
for i in range(nslots):
    raw = read_va(vt + 8 * i, 8)
    tgt = struct.unpack('<Q', raw)[0]
    print('slot %2d -> 0x%x  [%s]' % (i, tgt, sec_name(tgt)))
    code = read_va(tgt, 16 * ninsn) or b''
    for ins in md.disasm(code, tgt, ninsn):
        print('    %x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
