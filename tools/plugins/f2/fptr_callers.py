#!/usr/bin/env python3
"""PE 内の関数ポインタ表から、指定 VA の間接呼出し元を逆引きする (#2492)。

使い方: python3 fptr_callers.py <block_PE.bin> <VA> [<VA> ...]
各 VA について:
  0. VA 自身への参照: その値を格納する qword・rip 相対/絶対 disp・IMM (rel32 と即値。call/jmp/jcc を含む)・
     .text 内の 4 バイト即値一致の件数。0 件も出す (VA が格納・参照されないことの確認)。
  1. 囲む pdata 関数 F (間接 call で呼ばれる値は F の先頭)。
  2. F の値を格納する qword (全セクション・8 バイト境界の一致を含む全一致)。
  3. 格納先 S を含む表: S の前後で .text を指す qword が続く範囲 [a, b)。
  4. 表の各要素 E を参照する命令 (rip 相対・絶対 disp32) と、それを囲む pdata 関数、
     その関数への直接 call/jmp 元。F の直接 call/jmp 元と、.text 内の 4 バイト即値一致も出す。
"""
import bisect
import struct
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    pd = sec[b".pdata"]
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
        return funcs[i][0] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None

    def qword(va):
        return struct.unpack_from("<Q", img, va - base)[0]

    text = sec[b".text"]
    lo = base + text.VirtualAddress
    hi = lo + text.Misc_VirtualSize
    code = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    vas = [int(s, 16) for s in argv[2:]]
    fs = [enclosing(va) or va for va in vas]
    want = set(vas) | set(fs)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    refs = {}
    calls = {}
    imms = {}
    off = 0
    while off < len(code):
        got = False
        for ins in md.disasm(code[off:off + 16], lo + off, 1):
            got = True
            for op in ins.operands:
                if op.type == X86_OP_IMM and op.imm in want:
                    imms.setdefault(op.imm, []).append((ins.address, ins.mnemonic))
                if op.type != X86_OP_MEM:
                    continue
                if op.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                elif op.mem.base == 0 and op.mem.index == 0:
                    t = op.mem.disp
                else:
                    continue
                refs.setdefault(t, []).append((ins.address, ins.mnemonic, ins.op_str))
            if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == X86_OP_IMM:
                calls.setdefault(ins.operands[0].imm, []).append(ins.address)
            off += ins.size
        if not got:
            off += 1

    for va_s, va, F in zip(argv[2:], vas, fs):
        print(f"== {va_s}: enclosing pdata fn = {hex(F)}")
        print(f"  VA 自身 ({va_s}) への参照:")
        print(f"    qword 格納: {fmt([base + j for j in find_all(img, struct.pack('<Q', va))])}")
        print(f"    rip 相対・絶対 disp: {fmt([a for a, _, _ in refs.get(va, [])])}")
        print(f"    IMM (rel32・即値。call/jmp/jcc 含む): {fmt([a for a, _ in imms.get(va, [])])}")
        print(f"    .text 内の 4 バイト即値一致: {fmt([lo + i for i in find_all(code, struct.pack('<I', va))])}")
        print(f"  直接 call/jmp 元 ({hex(F)}): {fmt(calls.get(F, []))}")
        print(f"  .text 内の 4 バイト即値一致 ({hex(F)}): {[hex(lo + i) for i in find_all(code, struct.pack('<I', F))]}")
        slots = []
        j = img.find(struct.pack("<Q", F))
        while j != -1:
            slots.append(base + j)
            j = img.find(struct.pack("<Q", F), j + 1)
        print(f"  qword 格納 ({hex(F)}): {len(slots)} 件 {[hex(s) for s in slots[:8]]}")
        for s in slots[:8]:
            a = s
            while a - 8 >= base and lo <= qword(a - 8) < hi:
                a -= 8
            b = s
            while b + 8 <= base + len(img) and lo <= qword(b) < hi:
                b += 8
            print(f"  表 [{hex(a)}, {hex(b)}) = {(b - a) // 8} 要素 (.text を指す qword の連続)")
            for e in range(a, b, 8):
                hits = refs.get(e, [])
                if not hits:
                    continue
                print(f"    slot {hex(e)} -> {hex(qword(e))}")
                for addr, mn, ops in hits:
                    owner = enclosing(addr)
                    print(f"      参照 {hex(addr)} {mn} {ops} (囲む関数 {hex(owner) if owner else None})")
                    if owner:
                        print(f"        その関数への直接 call/jmp 元: {fmt(calls.get(owner, []))}")


def fmt(lst):
    return f"{len(lst)} 件 {[hex(a) for a in lst[:8]]}{' ...' if len(lst) > 8 else ''}"


def find_all(buf, pat):
    out = []
    i = buf.find(pat)
    while i != -1:
        out.append(i)
        i = buf.find(pat, i + 1)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv)
