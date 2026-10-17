#!/usr/bin/env python3
"""PY-5352 (#5493): 0x11c8950 の各直接 call 前に rdx へ入る値を解決する (実機不要)。

  python3 analysis/py5493_rdx.py <PE.bin> [--target 16b6d80] [--before 25]

各 call の前 N 命令の中で rdx を最後に書いた命令を探し、RIP 相対の参照先 (T) を
計算する。lea は rdx = T。mov は rdx = *(T) (qword)。*(T) が target (既定 0x16b6d80)
なら「target の値そのもの」、target の 8 バイト表 (VA 0x15dfd18 など) の中に target の
アドレスがある場合も同じく「&target」と判定する。rdx の書込みが窓内に無ければ unresolved。
"""
import argparse
import struct
from collections import deque

import capstone
import pefile

CALLEE = 0x11C8950
RDX_NAMES = {"rdx", "edx", "dx", "dl"}

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--target", default="16b6d80")
ap.add_argument("--before", type=int, default=25)
args = ap.parse_args()

target = int(args.target, 16)

pe = pefile.PE(args.path, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
with open(args.path, "rb") as f:
    f.seek(text.PointerToRawData)
    tdata = f.read(text.SizeOfRawData)
tbase = ib + text.VirtualAddress
image = pe.get_memory_mapped_image()


def qword_at(va):
    rva = va - ib
    if rva < 0 or rva + 8 > len(image):
        return None
    return struct.unpack_from("<Q", image, rva)[0]


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def describe(ins):
    t = rip_target(ins)
    if ins.mnemonic == "lea":
        return ("lea", t, t)
    if ins.mnemonic == "mov" and t is not None:
        v = qword_at(t)
        return ("mov", t, v)
    return ("other", None, None)


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

hist = deque(maxlen=args.before)
off = 0
n = 0
counts = {}
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    if ins.mnemonic == "call" and ins.operands[0].type == capstone.x86.X86_OP_IMM and ins.operands[0].imm == CALLEE:
        n += 1
        writer = None
        for h in reversed(hist):
            if h.mnemonic == "call":
                break
            if h.operands and h.operands[0].type == capstone.x86.X86_OP_REG and h.reg_name(h.operands[0].reg) in RDX_NAMES:
                writer = h
                break
        if writer is None:
            kind = "unresolved (rdx の書込みが窓内に無い)"
        else:
            how, t, v = describe(writer)
            if how == "lea":
                kind = "&global" if t == target else f"&{t:#x}" if t is not None else "lea (t 不明)"
            elif how == "mov" and v is not None and v == target:
                kind = f"*[{t:#x}] = target (=&global; 表経由)"
            elif how == "mov" and v is not None:
                kind = f"*[{t:#x}] = {v:#x}"
            else:
                kind = f"other: {writer.mnemonic} {writer.op_str}"
        counts[kind] = counts.get(kind, 0) + 1
        w = f"{writer.address:#x}: {writer.mnemonic} {writer.op_str}" if writer else "-"
        print(f"{ins.address:#x} call 0x11c8950 | rdx writer {w} | {kind}")
    hist.append(ins)

print(f"total call sites: {n}")
for k in sorted(counts):
    print(f"  {k}: {counts[k]}")
