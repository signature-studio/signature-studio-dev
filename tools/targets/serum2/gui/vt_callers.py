#!/usr/bin/env python3
"""SR-33 #2055: vtable 関数 VA の所属 vtable・RTTI と、その slot を間接 call する箇所を列挙する (静的)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法:
  1. 対象 slot VA (8 byte の .rdata 参照位置) から手前へ走査し、直前 8 byte が COL を指す vtable 先頭を探す。
     COL (signature=1) の pTypeDescriptor から RTTI クラス名を得る。
  2. vtable 先頭への rip 相対 lea (vtable 生成・代入箇所) を列挙する。
  3. .text 内の `call qword ptr [reg + disp]` のうち disp が指定値のものを列挙する (候補。宛先のクラスは未解決)。
usage: vt_callers.py <pe> <slot_va_hex> [...] [--disp 0x30,0x38]
"""
import bisect
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

args = sys.argv[1:]
disps = [0x30, 0x38, 0x88]
if "--disp" in args:
    i = args.index("--disp")
    disps = [int(x, 16) for x in args[i + 1].split(",")]
    del args[i:i + 2]
pe = pefile.PE(args[0])
data = open(args[0], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
slots = [int(a, 16) for a in args[1:]]


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


def cstr(va):
    off = rva_to_off(va)
    return data[off:data.index(b"\0", off)].decode(errors="replace")


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
    return funcs[k][0] if k >= 0 and funcs[k][0] <= va < funcs[k][1] else None


def find_head(slot):
    for k in range(64):
        h = slot - 8 * k
        col = rq(h - 8)
        if IMG <= col < IMG + 0x10000000:
            o = rva_to_off(col)
            sig, _, _, td_rva, _ = struct.unpack_from("<IIIII", data, o)
            if sig == 1:
                return h, k, cstr(IMG + td_rva + 16)
    return None, None, "?"


md = Cs(CS_ARCH_X86, CS_MODE_64)
code = text.get_data()
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
ind_re = re.compile(r"qword ptr \[(\w+) \+ (0x[0-9a-f]+)\]")
ins_all = list(md.disasm(code, t_base))

heads = {}
for s in slots:
    h, k, name = find_head(s)
    heads[s] = h
    print(f"slot {s:#x}: vtable head={h:#x} index={k} RTTI={name} func={func_of(s) or 0:#x}")

for s in slots:
    h = heads[s]
    refs = []
    for ins in ins_all:
        m = rip_re.search(ins.op_str)
        if m and h is not None:
            d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            if ins.address + ins.size + d == h:
                refs.append(ins.address)
    print(f"== lea/rip refs to vtable head {h:#x}: " + ", ".join(f"{a:#x} (in {func_of(a) or 0:#x})" for a in refs))

print(f"== indirect `call qword ptr [reg+disp]` with disp in {[hex(d) for d in disps]} (candidates, receiver unresolved)")
n = 0
for ins in ins_all:
    if ins.mnemonic != "call":
        continue
    m = ind_re.search(ins.op_str)
    if m and int(m.group(2), 16) in disps:
        n += 1
        print(f"  {ins.address:#x} call [{m.group(1)}+{m.group(2)}] in func {func_of(ins.address) or 0:#x}")
print(f"total={n}")
