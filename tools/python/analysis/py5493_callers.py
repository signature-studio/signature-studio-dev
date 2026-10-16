#!/usr/bin/env python3
"""PY-5352 (#5493): 指定 VA への直接 call の呼び出し元を列挙する (実機不要)。

  python3 analysis/py5493_callers.py <PE.bin> <target VA hex> [<target VA hex> ...] [--before N]

各 call の前 N 命令 (既定 25) を出す。全命令は保持せず逐次走査する。
"""
import argparse
from collections import deque

import capstone
import pefile

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("targets", nargs="+")
ap.add_argument("--before", type=int, default=25)
args = ap.parse_args()

targets = {int(t, 16) for t in args.targets}

pe = pefile.PE(args.path, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
with open(args.path, "rb") as f:
    f.seek(text.PointerToRawData)
    tdata = f.read(text.SizeOfRawData)
tbase = ib + text.VirtualAddress

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

hist = deque(maxlen=args.before)
off = 0
n = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    if ins.mnemonic == "call" and ins.operands[0].type == capstone.x86.X86_OP_IMM and ins.operands[0].imm in targets:
        n += 1
        print(f"== call {ins.operands[0].imm:#x} at {ins.address:#x} (before {args.before}) ==")
        for h in hist:
            print("    " + h)
        print(f"  * {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    hist.append(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
print(f"total call sites: {n}")
