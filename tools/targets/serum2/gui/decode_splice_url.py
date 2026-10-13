#!/usr/bin/env python3
"""Decode the XOR-obfuscated literal built on the stack by SpliceController's button handler
(0x180796320). The function copies 0x4c bytes from .rdata with movups/movaps into [rsp+0x20..],
then XORs byte i with (i - 0x6a) & 0xff. usage: decode_splice_url.py <Serum2_win64.vst3> [fn VA hex]"""
import sys, re
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1]); IMG = pe.OPTIONAL_HEADER.ImageBase
dm = pe.get_memory_mapped_image()
fn = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x180796320
N, KEY, BASE = 0x4c, 0x6a, 0x20

buf = bytearray(N)
pending = None
for ins in Cs(CS_ARCH_X86, CS_MODE_64).disasm(dm[fn - IMG:fn - IMG + 0x200], fn):
    if ins.mnemonic in ('movups', 'movaps') and ins.op_str.startswith('xmm') and '[rip' in ins.op_str:
        disp = int(re.search(r'\[rip \+ (0x[0-9a-f]+)\]', ins.op_str).group(1), 16)
        pending = ins.address + ins.size + disp - IMG
    elif ins.mnemonic in ('movups', 'movaps') and ins.op_str.startswith('xmmword ptr [rsp + ') and pending is not None:
        off = int(re.search(r'\[rsp \+ (0x[0-9a-f]+)\]', ins.op_str).group(1), 16) - BASE
        if 0 <= off < N:
            w = min(16, N - off)
            buf[off:off + w] = dm[pending:pending + w]
        pending = None
    if ins.mnemonic == 'cmp' and ins.op_str == 'rax, 0x4c':
        break

print(repr(bytes(b ^ ((i - KEY) & 0xFF) for i, b in enumerate(buf)).decode('latin1')))
