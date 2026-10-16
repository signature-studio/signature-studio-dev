#!/usr/bin/env python3
"""PY-5352 (#5493): global 0x16b6d80 の書込み元を辿る (実機不要・近似)。

  python3 analysis/py5493_writer.py <PE.bin> [--dis FN_VA_HEX ...] [--ctx N] [--nins N]

1. ポインタ表 0x15dfd18 を RIP 相対で読む命令 (table refs) の前後 ctx 命令を出す。
2. --dis で指定した VA から始まる関数の先頭 nins 命令を逆アセンブルする。
全命令を保持せず、逐次走査で処理する (メモリ使用を抑える)。
"""
import argparse
from collections import deque

import capstone
import pefile

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--glob", default="16b6d80")
ap.add_argument("--tbl", default="15dfd18")
ap.add_argument("--dis", nargs="*", default=["11c8950", "86a470"])
ap.add_argument("--nins", type=int, default=40)
ap.add_argument("--ctx", type=int, default=2)
args = ap.parse_args()

TBL = int(args.tbl, 16)
G = int(args.glob, 16)

pe = pefile.PE(args.path, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
with open(args.path, "rb") as f:
    f.seek(text.PointerToRawData)
    tdata = f.read(text.SizeOfRawData)
tbase = ib + text.VirtualAddress

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def stream():
    off = 0
    n = len(tdata)
    while off < n:
        ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        yield ins


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def fmt(ins):
    return f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}"


# pass 1: table refs with context
print("== table refs (%#x) ==" % TBL)
before = deque(maxlen=args.ctx)
pending = 0
after_lines = []
refs = 0
for ins in stream():
    if pending > 0:
        print("    " + fmt(ins))
        pending -= 1
    if rip_target(ins) == TBL:
        refs += 1
        print(f"-- ref {ins.address:#x}")
        for b in before:
            print("    " + b)
        print("  * " + fmt(ins))
        pending = args.ctx
        before.clear()
        continue
    before.append("    " + fmt(ins))
print(f"table refs: {refs}")

# pass 2: direct disassembly of the given functions
wanted = {int(x, 16): x for x in args.dis}
remaining = dict(wanted)
emit = {}
for ins in stream():
    if ins.address in remaining:
        emit[ins.address] = 0
        print(f"== fn {ins.address:#x} ==")
        del remaining[ins.address]
    for a in list(emit):
        if emit[a] < args.nins:
            print("    " + fmt(ins))
            emit[a] += 1
    if not remaining and all(v >= args.nins for v in emit.values()):
        break
