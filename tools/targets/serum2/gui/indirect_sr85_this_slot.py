#!/usr/bin/env python3
"""SR-85 #5934: 閉包内の間接 call のうち、受信が所属関数の this (vptr:THIS) のものを、this の class の vtable に絞る (静的)。

入力: PE・indirect_sr85_join_recv.py の出力 (join.tsv: site / in_func / operand / recv_strict / recv_loose / matched)。
手順:
  1. indirect_sr85_all_vt.py と同じ方法で全 vtable (COL 付き) と vptr 構築済み vtable を集める。
  2. join.tsv の recv_strict が vptr:THIS の行について、所属関数 in_func を slot に持つ vtable を探し、その class 名の集合 C を得る。
  3. 候補 slot k = disp/8 について、構築済み vtable のうち class 名が C に入るものの slot k の関数を候補にする。
出力: 1 行 1 サイト の TSV (site / in_func / operand / owner_classes / all_constructed_cands / restricted_cands)。
      owner (in_func を slot に持つ vtable) が無いサイトは restricted を "-" とする。
usage: indirect_sr85_this_slot.py <pe> <join.tsv>
"""
import re
import struct
import sys

import pefile

pe_path, join_path = sys.argv[1], sys.argv[2]
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_lo = IMG + text.VirtualAddress
t_hi = t_lo + max(text.Misc_VirtualSize, text.SizeOfRawData)
rdata_secs = [s for s in pe.sections if s.Name.rstrip(b"\0") in (b".rdata", b".data")]


def off_of(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def td_name(td_rva):
    o = off_of(td_rva + 0x10)
    if o is None:
        return "?"
    e = data.find(b"\x00", o, o + 512)
    return data[o:e].decode(errors="replace") if e > 0 else "?"


vtables = []  # (vt_va, class_name, [slot VA...])
for s in rdata_secs:
    lo = s.PointerToRawData
    hi = lo + s.SizeOfRawData
    for o in range(lo, hi - 7, 8):
        v = struct.unpack_from("<Q", data, o)[0]
        col_rva = v - IMG
        co = off_of(col_rva) if 0 < col_rva < 0x10000000 else None
        if co is None or co + 0x18 > len(data):
            continue
        if struct.unpack_from("<I", data, co)[0] != 1:
            continue
        if struct.unpack_from("<I", data, co + 0x14)[0] != col_rva:
            continue
        td_rva = struct.unpack_from("<I", data, co + 0x0C)[0]
        name = td_name(td_rva)
        slots = []
        p = o + 8
        while p + 8 <= len(data):
            w = struct.unpack_from("<Q", data, p)[0]
            if not (t_lo <= w < t_hi):
                break
            slots.append(w)
            p += 8
        if slots:
            vtables.append((IMG + (o - lo + s.VirtualAddress) + 8, name, slots))

# vptr 構築 (indirect_sr85_all_vt.py と同じ判定)
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from collections import defaultdict

code = text.get_data()[: t_hi - t_lo]
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
store_re = re.compile(r"^qword ptr \[[^\]]+\], (r[a-z0-9]+)$")
md = Cs(CS_ARCH_X86, CS_MODE_64)
insns = list(md.disasm(code, t_lo))
lea_targets = defaultdict(int)
for i, ins in enumerate(insns):
    if ins.mnemonic != "lea":
        continue
    m = rip_re.search(ins.op_str)
    if not m:
        continue
    reg = ins.op_str.split(",")[0].strip()
    ea = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    for nxt in insns[i + 1 : i + 4]:
        if nxt.mnemonic == "mov":
            sm = store_re.match(nxt.op_str)
            if sm and sm.group(1) == reg:
                lea_targets[ea] += 1
                break
        if nxt.mnemonic in ("call", "jmp", "ret"):
            break
constructed = [v for v in vtables if lea_targets.get(v[0], 0) > 0]

rows = []
with open(join_path) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 6:
            continue
        site, in_func, operand, strict = cols[0], cols[1], cols[2], cols[3]
        if strict != "vptr:THIS" or not in_func or in_func == "-":
            continue
        rows.append((site, in_func, operand))

print("site\tin_func\toperand\towner_classes\tall_constructed_cands\trestricted_cands")
for site, in_func, operand in rows:
    k = int(operand[operand.index("+") + 1 : -1], 16) // 8
    fva = int(in_func, 16)
    owners = {name for _, name, slots in vtables if fva in slots}
    all_c = {slots[k] for _, _, slots in constructed if k < len(slots)}
    if not owners:
        print(f"{site}\t{in_func}\t{operand}\t-\t{len(all_c)}\t-")
        continue
    restr = {slots[k] for _, name, slots in constructed if k < len(slots) and name in owners}
    print(f"{site}\t{in_func}\t{operand}\t{','.join(sorted(owners))}\t{len(all_c)}\t{len(restr)}")
