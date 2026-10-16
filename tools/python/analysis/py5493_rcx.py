#!/usr/bin/env python3
"""PY-5352 (#5493): 0x11be444 の呼出し引数 rcx の出所を RIP 相対で辿る (実機不要)。

  python3 analysis/py5493_rcx.py <PE.bin>

1. 0x11be436 の `mov rcx, [rip+disp]` の解決先 (global G1) を出す。
2. G1 を RIP 相対で指す命令を全域で列挙する (読出し/書込みの区別つき)。
全命令は保持せず逐次走査する。
"""
import argparse

import capstone
import pefile

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--site", default="11be436")
args = ap.parse_args()

pe = pefile.PE(args.path, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
with open(args.path, "rb") as f:
    f.seek(text.PointerToRawData)
    tdata = f.read(text.SizeOfRawData)
tbase = ib + text.VirtualAddress

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def ins_at(va):
    off = va - tbase
    return next(md.disasm(tdata[off:off + 15], va, 1), None)


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


site = int(args.site, 16)
ins = ins_at(site)
g1 = rip_target(ins)
print(f"site {ins.address:#x}: {ins.mnemonic} {ins.op_str} -> global {g1:#x}")

# 全域走査: G1 を RIP 相対で指す命令
off = 0
n = len(tdata)
hits = []
while off < n:
    i = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if i is None:
        off += 1
        continue
    off += i.size
    if rip_target(i) == g1:
        hits.append(i)
print(f"refs to {g1:#x}: {len(hits)}")
for h in hits:
    kind = "write" if h.mnemonic in ("mov",) and h.operands and h.operands[0].type == capstone.x86.X86_OP_MEM else "read"
    print(f"  {h.address:#x}: {h.mnemonic} {h.op_str}  [{kind}]")
