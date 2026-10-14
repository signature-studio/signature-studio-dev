#!/usr/bin/env python3
"""PE 内で VA を参照する箇所を列挙する (#2303)。

使い方: python3 fn_refs.py <block_PE.bin> <VA> [<VA> ...]
各 VA について: 囲む pdata 関数、直接 call/jmp (rel32)、
qword 格納 (絶対 VA)、rip 相対参照 (lea/mov/call qword ptr)、絶対 disp 参照、即値 (imm) 参照を出す。
"""
import bisect
import os
import struct
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
    raw = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
    funcs = []
    for i in range(0, len(raw) - 11, 12):
        b, e, _ = struct.unpack_from("<III", raw, i)
        if b == 0:
            break
        funcs.append((base + b, base + e))
    funcs.sort()
    starts = [f[0] for f in funcs]

    def enclosing(a):
        i = bisect.bisect_right(starts, a) - 1
        return funcs[i] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None

    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    rva = text.VirtualAddress
    code = img[rva:rva + text.Misc_VirtualSize]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rip_refs = {}
    abs_refs = {}
    imm_refs = {}
    off = 0
    while off < len(code):
        got = False
        for ins in md.disasm(code[off:off + 16], base + rva + off, 1):
            got = True
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    rip_refs.setdefault(ins.address + ins.size + op.mem.disp, []).append(
                        (ins.address, ins.mnemonic, ins.op_str))
                elif op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                    abs_refs.setdefault(op.mem.disp & 0xFFFFFFFFFFFFFFFF, []).append(
                        (ins.address, ins.mnemonic, ins.op_str))
                elif op.type == X86_OP_IMM:
                    imm_refs.setdefault(op.imm & 0xFFFFFFFFFFFFFFFF, []).append(
                        (ins.address, ins.mnemonic, ins.op_str))
            off += ins.size
        if not got:
            off += 1

    for va_s in argv[2:]:
        va = int(va_s, 16)
        f = enclosing(va)
        print(f"== {va_s}: enclosing pdata fn = {hex(f[0]) if f else None}")
        callers = []
        for i in range(len(code) - 5):
            if code[i] in (0xE8, 0xE9):
                r = struct.unpack_from("<i", code, i + 1)[0]
                if base + rva + i + 5 + r == va:
                    callers.append(hex(base + rva + i))
        print("  rel32 call/jmp:", callers)
        qs = []
        t = struct.pack("<Q", va)
        j = img.find(t)
        while j != -1:
            qs.append(hex(base + j))
            j = img.find(t, j + 1)
        print("  qword store:", qs)
        for a, m, s in rip_refs.get(va, []):
            print(f"  rip-ref: {hex(a)} {m} {s}")
        for a, m, s in abs_refs.get(va, []):
            print(f"  abs-ref: {hex(a)} {m} {s}")
        for a, m, s in imm_refs.get(va, []):
            print(f"  imm-ref: {hex(a)} {m} {s}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv)
