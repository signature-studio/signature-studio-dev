#!/usr/bin/env python3
"""SR-76 #4484: 関数 T (例: `0x1803573f0`) の呼出元の上界集合 S を静的に求める。
S = (a) T の direct 逆閉包 R の外からの direct call
  + (b) R の関数ポインタを格納する vtable スロットと同じ disp で `call [reg+disp]` している関数 (間接 call の上界)
  + (c) R の関数アドレスを rip 相対で materialise している関数。
R の vtable スロットは .rdata/.data の 8 byte 完全一致で求め、(vtable head, index) から disp = index*8 を出す。
限界: `call reg` (レジスタ値の間接 call) と `call [rsp+disp]` の宛先は解決しない (disp が R のものと一致する
`[rsp+disp]` は (b) に含む)。よって S は『R の vtable スロット経由の呼出し』に対する上界であり、
レジスタ値経由の間接 call を含む完全な呼出元集合ではない (未解決は REPORT_SR76 §5 参照)。
usage: indirect_upper_bound.py <pe> <target_va_hex> <root_va_hex>
  root: 閉包 C を取る根 (setState 0x1800c2b50・getState 0x1800c6090)。S と C・demo bit 関数 (0x22792 を参照する関数) との交わりを出す。
"""
import re
import struct
import sys
from collections import defaultdict, deque

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, target, root = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
tb = IMG + text.VirtualAddress
te = tb + text.Misc_VirtualSize
raw = text.get_data()
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.append((IMG + b, IMG + e))
sset = {f[0] for f in funcs}

cs = Cs(CS_ARCH_X86, CS_MODE_64)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem_re = re.compile(r"^qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]$")
fwd = defaultdict(set)
rev = defaultdict(set)
ind = []  # (call 命令 VA, 所属関数, disp, オペランド)
ripref = defaultdict(list)  # 参照先 VA -> [(命令 VA, 所属関数)]
demo = set()  # 0x22792 (demo bit) を参照する関数
for lo, hi in funcs:
    for ins in cs.disasm(raw[lo - tb:hi - tb], lo):
        if re.search(r"\+ 0x22792\]", ins.op_str):
            demo.add(lo)
        m = rip_re.search(ins.op_str)
        if m:
            ea = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            ripref[ea].append((ins.address, lo))
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if t in sset and t != lo:
                fwd[lo].add(t)
                rev[t].add(lo)
        if ins.mnemonic == "call":
            mm = mem_re.match(ins.op_str)
            if mm:
                ind.append((ins.address, lo, int(mm.group(2), 0) if mm.group(2) else 0, ins.op_str))


def closure(seed, edges):
    seen = {seed}
    q = deque([seed])
    while q:
        f = q.popleft()
        for g in edges.get(f, ()):
            if g not in seen:
                seen.add(g)
                q.append(g)
    return seen


R = closure(target, rev)
C = closure(root, fwd)

rd = sec[b".rdata"]
rraw = rd.get_data()
rbase = IMG + rd.VirtualAddress
disps = set()
slot_desc = []
for s in (rd, sec[b".data"]):
    sraw = s.get_data()
    base = IMG + s.VirtualAddress
    for off in range(0, len(sraw) - 7, 8):
        v = struct.unpack_from("<Q", sraw, off)[0]
        if v not in R:
            continue
        sva = base + off
        if not (rbase <= sva < rbase + len(rraw)):
            slot_desc.append(f"{sva:#x}(.data)->{v:#x}")
            continue
        h = sva
        while h - 8 >= rbase:
            p = struct.unpack_from("<Q", rraw, h - 8 - rbase)[0]
            if not (tb <= p < te):
                break
            h -= 8
        disps.add(sva - h)
        slot_desc.append(f"{sva:#x}->{v:#x} (vtable {h:#x} index {(sva - h) // 8})")

S_direct = set().union(*(rev[x] for x in R)) - R
S_ind = {fn for _, fn, d, _ in ind if d in disps}
S_rip = {fn for x in R for _, fn in ripref.get(x, [])}
S = S_direct | S_ind | S_rip

print(f"target {target:#x}: R={len(R)} (direct reverse closure)  root {root:#x}: C={len(C)}  C∩R={len(C & R)}")
print("R vtable slots: " + ("; ".join(slot_desc) if slot_desc else "(none)"))
print("R disps: " + " ".join(hex(d) for d in sorted(disps)))
print(f"S (upper bound of callers): direct {len(S_direct)} | indirect call [reg+disp] {len(S_ind)} | rip-materialised {len(S_rip)} | total {len(S)}")
print(f"demo-bit functions (0x22792 operand): {len(demo)} {sorted(hex(x) for x in demo)}")
print(f"S ∩ demo-bit = {len(S & demo)} {sorted(hex(x) for x in S & demo)}")
print(f"S ∩ C = {len(S & C)} (root closure)  S ∩ C ∩ demo = {len(S & C & demo)}")
