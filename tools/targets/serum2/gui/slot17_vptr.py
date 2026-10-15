#!/usr/bin/env python3
"""SR-53 #3398: slot 17 `0x1800c9680` を間接 call で呼べる vptr 定数の候補を全 .text から列挙する (静的)。

考え方: 関数ポインタ `F` を格納するデータ slot `S` (.rdata/.data の 8 byte) は slot_reach.py の
「address-taken」出力で求める。受信オブジェクトの vptr が V のとき、`call [reg+disp]` が S を読むのは
V + disp == S のとき。V は .text 内の rip 相対 lea/mov で参照される定数 (ctor が vptr を書く形) に限る。
したがって候補は「S - disp を指す rip 相対参照が .text にあるか」で決まる。

限界: vptr を別オブジェクトからコピーする経路 (copy ctor 等) は見ていない。.text 外の vptr 書込みも見ていない。
usage: slot17_vptr.py <pe> <slot_va_hex> [--disp-set <hex>,...]
"""
import bisect
import re
import struct
import sys
from collections import defaultdict

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import pefile

pe_path = sys.argv[1]
slot = int(sys.argv[2], 16)
disp_set = set()
if "--disp-set" in sys.argv:
    for x in sys.argv[sys.argv.index("--disp-set") + 1].split(","):
        disp_set.add(int(x, 16))

pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_base = IMG + text.VirtualAddress
t_end = t_base + text.Misc_VirtualSize
code = text.get_data()
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for k in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, k)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()

md = Cs(CS_ARCH_X86, CS_MODE_64)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem88_re = re.compile(r"^qword ptr \[(r[a-z0-9]+) \+ 0x88\]$")
starts = {lo for lo, _ in funcs}
refs = defaultdict(list)  # 参照先 VA -> [(命令 VA, 命令)]
fwd = defaultdict(set)  # 関数 -> direct call/jmp の宛先 (開始点のみ)
calls88 = defaultdict(list)  # 関数 -> [(命令 VA, 命令)] の call [reg+0x88]
for lo, hi in funcs:
    for ins in md.disasm(code[lo - t_base:hi - t_base], lo):
        m = rip_re.search(ins.op_str)
        if m:
            ea = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            refs[ea].append((ins.address, f"{ins.mnemonic} {ins.op_str}"))
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            try:
                tgt = int(ins.op_str, 16)
            except ValueError:
                continue
            if tgt in starts and tgt != lo:
                fwd[lo].add(tgt)
        if ins.mnemonic == "call" and mem88_re.match(ins.op_str.strip()):
            calls88[lo].append((ins.address, ins.op_str))


def closure(seeds):
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        f = stack.pop()
        for g in fwd.get(f, ()):
            if g not in seen:
                seen.add(g)
                stack.append(g)
    return seen


ctor = None
for a in ("--ctor",):
    if a in sys.argv:
        ctor = int(sys.argv[sys.argv.index(a) + 1], 16)
if ctor is not None:
    K = closure([ctor])
    hits = [(f, a, op) for f in sorted(calls88) if f in K for a, op in calls88[f]]
    print(f"ctor {ctor:#x}: direct closure {len(K)} funcs; call [reg+0x88] sites in it: {len(hits)}")
    for f, a, op in hits:
        print(f"  {a:#x} in {f:#x}: call {op}")
    print(f"whole .text call [reg+0x88] sites: {sum(len(v) for v in calls88.values())}")

rd = sec(b".rdata")
rraw = rd.get_data()
rbase = IMG + rd.VirtualAddress


def rval(va):
    off = va - rbase
    if off < 0 or off + 8 > len(rraw):
        return None
    return struct.unpack_from("<Q", rraw, off)[0]


print(f"slot {slot:#x}: .rdata value = {rval(slot):#x}" if rval(slot) is not None else f"slot {slot:#x}: outside .rdata")
print(f"rip-relative reference targets in .text: {len(refs)}")
cands = []
for ea in sorted(refs):
    d = slot - ea
    if 0 <= d <= 0x2000 and d % 8 == 0:
        head_ok = rval(ea) is not None and t_base <= rval(ea) < t_end
        cands.append((d, ea, head_ok))
print(f"candidate vptr constants V (V + disp == slot, disp <= 0x2000, multiple of 8): {len(cands)}")
for d, ea, head_ok in cands:
    if disp_set and d not in disp_set:
        continue
    fns = sorted({lo for lo, hi in funcs for a, _ in refs[ea] if lo <= a < hi})
    print(f"  V {ea:#x}  disp {d:#x}  V[0] is .text ptr: {head_ok}  refs {len(refs[ea])} in {len(fns)} funcs")
    for a, ins in refs[ea][:8]:
        print(f"      {a:#x}: {ins}")
