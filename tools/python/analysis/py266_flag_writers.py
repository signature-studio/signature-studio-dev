#!/usr/bin/env python3
"""PY-266 (#3890): flag `byte [[[0x15e14a0]]+0x7e0+0x49e]` の書込み元を、全 PE block の .text で列挙する。

  FL_WIN64_DIR=<展開先> python3 analysis/py266_flag_writers.py [--mutate]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*_PE.bin' (313 block)

方式: flag の番地は [reg+0x49e] (disp32) で書かれる。0x49e を覆う書込みは disp d (0x497..0x49e) の
disp32 を持つ命令なので、生バイト列の 4 byte 一致で候補を作り、その直前 15 byte から復号して
「メモリ operand の disp が d」かつ「命令が p を含む」ものだけを採る (線形走査はしない)。
幅 w の書込みが 0x49e を覆うのは d <= 0x49e < d + w のとき。命令の先頭オペランドがその memory operand で、
mnemonic が書込み系なら write、lea なら addr、それ以外 (読出し・cmp・test) は read として数える。
所属関数は x64 の .pdata (RUNTIME_FUNCTION)。i386 は .pdata が無いので所属は "-" にする。
--mutate: 既知の書込み (block00031 の 0x737574 `mov byte ptr [rbx+0x49e], dl`) の disp を 1 bit 変えたメモリ上の複製で
検出器を走らせ、その命令が write として出ないことを確かめる (ネガティブコントロール)。
"""
import glob
import os
import struct
import sys

import capstone
import pefile

DIR = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
TARGET = 0x49E
DISPS = range(TARGET - 7, TARGET + 1)
WRITE_PREFIX = ("mov", "set", "and", "or", "add", "sub", "xor", "inc", "dec", "neg", "not",
                "adc", "sbb", "shl", "shr", "sar", "rol", "ror", "xadd", "cmpxchg", "bts", "btr", "btc")
KNOWN = 0x737574
BLOCK00031 = "block00031_PE.bin"


def runtime_funcs(pe):
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    ents = getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", [])
    return sorted((e.struct.BeginAddress, e.struct.EndAddress) for e in ents)


def owner(funcs, rva):
    lo, hi = 0, len(funcs)
    while lo < hi:
        mid = (lo + hi) // 2
        if funcs[mid][0] <= rva:
            lo = mid + 1
        else:
            hi = mid
    if lo and funcs[lo - 1][0] <= rva < funcs[lo - 1][1]:
        return funcs[lo - 1][0]
    return None


def classify(ins, d, w):
    mem = next((op for op in ins.operands if op.type == capstone.x86.X86_OP_MEM and op.mem.disp == d), None)
    if mem is None:
        return "read"
    if mem.mem.base == capstone.x86.X86_REG_RIP:
        return "rip"
    if ins.mnemonic == "lea":
        return "addr"
    dst = ins.operands[0]
    covers = d <= TARGET < d + w
    if dst.type == capstone.x86.X86_OP_MEM and dst.mem.disp == d and covers and ins.mnemonic.startswith(WRITE_PREFIX):
        return "write"
    return "read"


def src_kind(ins):
    if len(ins.operands) < 2:
        return "-"
    src = ins.operands[1]
    if src.type == capstone.x86.X86_OP_IMM:
        return f"imm {src.imm:#x}"
    if src.type == capstone.x86.X86_OP_REG:
        return f"reg {ins.reg_name(src.reg)}"
    if src.type == capstone.x86.X86_OP_MEM:
        return "mem"
    return "other"


def find_hits(md, raw, text_off, text_len, base_va):
    out = {}
    for d in DISPS:
        pat = struct.pack("<I", d)
        p = raw.find(pat, text_off, text_off + text_len)
        while p != -1:
            for s in range(max(text_off, p - 15), p):
                ins = next(md.disasm(raw[s:s + 16], base_va + (s - text_off), 1), None)
                if ins is None or s + ins.size < p + 4:
                    continue
                if any(op.type == capstone.x86.X86_OP_MEM and op.mem.disp == d for op in ins.operands):
                    out.setdefault(ins.address, (ins, d, next(
                        (op.size for op in ins.operands if op.type == capstone.x86.X86_OP_MEM), 8) or 8))
                break
            p = raw.find(pat, p + 1, text_off + text_len)
    return out


def scan_block(raw, pe, mode, mutate_at=None):
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    text_off = text.PointerToRawData
    text_len = min(text.Misc_VirtualSize, text.SizeOfRawData)
    base_va = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    if mutate_at is not None:
        raw = bytearray(raw)
        q = mutate_at - base_va + text_off
        at = bytes(raw[q:q + 16]).find(struct.pack("<I", TARGET))
        raw[q + at] ^= 0x01
        raw = bytes(raw)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64 if mode == 64 else capstone.CS_MODE_32)
    md.detail = True
    return find_hits(md, raw, text_off, text_len, base_va)


def main():
    mutate = "--mutate" in sys.argv
    counts = {"write": 0, "addr": 0, "read": 0, "rip": 0}
    rows = []
    for p in sorted(glob.glob(os.path.join(DIR, "*_PE.bin"))):
        raw = open(p, "rb").read()
        pe = pefile.PE(data=raw, fast_load=True)
        mach = pe.FILE_HEADER.Machine
        if mach not in (0x8664, 0x14C):
            continue
        mode = 64 if mach == 0x8664 else 32
        funcs = runtime_funcs(pe) if mode == 64 else []
        ib = pe.OPTIONAL_HEADER.ImageBase
        if not any(s.Name.rstrip(b"\0") == b".text" for s in pe.sections):
            continue
        hits = scan_block(raw, pe, mode)
        for addr, (ins, d, w) in sorted(hits.items()):
            kind = classify(ins, d, w)
            counts[kind] += 1
            if kind != "write":
                continue
            fn = owner(funcs, addr - ib) if funcs else None
            mem = next(op for op in ins.operands if op.type == capstone.x86.X86_OP_MEM and op.mem.disp == d)
            w = mem.size or 8
            rows.append((os.path.basename(p), hex(addr), f"disp={d:#x}", f"w={w}", f"{ins.mnemonic} {ins.op_str}",
                         src_kind(ins), hex(fn + ib) if fn is not None else "-"))
    for r in rows:
        print("\t".join(r))
    print("counts", counts)
    if mutate:
        ib = 0x400000
        pe = pefile.PE(os.path.join(DIR, BLOCK00031), fast_load=True)
        raw = open(os.path.join(DIR, BLOCK00031), "rb").read()
        hits = scan_block(raw, pe, 64, mutate_at=KNOWN)
        hit = hits.get(KNOWN)
        ok = hit is None or classify(hit[0], hit[1], hit[2]) != "write"
        print("mutate", "PASS" if ok else "FAIL", "at", hex(KNOWN), "rc", 0 if ok else 1)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
