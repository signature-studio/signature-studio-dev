#!/usr/bin/env python3
"""SR-38 #2102: SerumController vtable (head VA) の間接 call 候補 (call [reg+disp]) の受信型を分類する (静的・ヒューリスティック)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
disp は vtable slot 番号 * 8 に対応する (slot 6 = 0x30 / slot 7 = 0x38 / slot 17 = 0x88)。
分類 (候補ごと・所属関数 F 単位。受信型は証明しない。F の中の call が受信型まで SerumController だとは限らない):
  S: F が同 vtable の slot 関数 (受信 this の型の候補は SerumController だが、call の受信は this とは限らない)。
  K: F 内に vtable head への rip 相対 lea がある (F 内で SerumController を構築・代入)。
  U: 上記以外 (未解決)。
注意: 受信レジスタ (rax 等) の出自 (this / 子オブジェクト / 別オブジェクト) は逆解析していない。
  S/K は「受信型を解決する作業の起点」であり、受信型の確定ではない。
usage: serum_controller_recv.py <pe> <vtable_head_hex> <slot_index> [<slot_index> ...]
  slot_index 指定の disp (slot*8) の候補のみ分類する。
"""
import bisect
import re
import struct
import sys
from collections import Counter

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
head = int(sys.argv[2], 16)
slot_ids = [int(x) for x in sys.argv[3:]]
disps = {s * 8 for s in slot_ids}


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


def rva_to_off(va):
    rva = va - IMG
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def rq(va):
    return struct.unpack_from("<Q", data, rva_to_off(va))[0]


text = sec(b".text")
t_base = IMG + text.VirtualAddress
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]


def func_of(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


slot_fns = set()
for k in range(64):
    v = rq(head + 8 * k)
    if v == 0:
        break
    slot_fns.add(v)

md = Cs(CS_ARCH_X86, CS_MODE_64)
ins_all = list(md.disasm(text.get_data(), t_base))
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem_re = re.compile(r"^qword ptr \[(r(?!ip\b)[a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]$")

ctor_fns = set()
for ins in ins_all:
    m = rip_re.search(ins.op_str)
    if m:
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        if ins.address + ins.size + d == head:
            ctor_fns.add(func_of(ins.address))

cands = []
for ins in ins_all:
    if ins.mnemonic != "call":
        continue
    c = mem_re.search(ins.op_str.strip())
    if not c:
        continue
    disp = int(c.group(2), 16) if c.group(2) else 0
    if disp in disps:
        cands.append((ins.address, func_of(ins.address), c.group(1), disp))

cls = Counter()
rows = {"S": [], "K": [], "U": []}
for a, f, reg, disp in cands:
    if f in slot_fns:
        k = "S"
    elif f in ctor_fns:
        k = "K"
    else:
        k = "U"
    cls[k] += 1
    rows[k].append((a, f, reg, disp))

print(f"vtable head {head:#x} slots={slot_ids} candidates={len(cands)}")
print(f"slot functions (all, non-null): {len(slot_fns)}  ctor-like functions (lea to head): {sorted(hex(x) for x in ctor_fns if x)}")
print(f"S (enclosing fn is a slot fn of the vtable; receiver NOT proven): {cls['S']}")
print(f"K (enclosing fn has lea to head; receiver NOT proven): {cls['K']}")
print(f"U (unresolved): {cls['U']}")
for k in ("S", "K"):
    print(f"== {k} ==")
    for a, f, reg, disp in rows[k]:
        print(f"{a:#x} in {f or 0:#x}  call [{reg}+{disp:#x}]")
