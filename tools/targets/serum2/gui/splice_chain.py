#!/usr/bin/env python3
"""SR-30 #2000: 関数先頭 VA の参照元を列挙する (静的・.pdata 境界付き)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
列挙するもの:
  1. .text 内の直接 call/jmp (rel32 で対象 VA を指すもの)。
  2. .text 内の rip 相対オペランドが対象 VA を指すもの (lea 等で関数ポインタを作る箇所)。
  3. .rdata / .data の 8 byte スロットが対象 VA を持つもの (vtable・関数ポインタ表)。
  4. .rdata の 4 byte スロットが (対象 VA - ImageBase) の RVA を持つもの (MSVC 相対 switch 表等)。
各参照は所属関数 (.pdata 境界) を併記する。
限界: レジスタ経由の間接 call (call [reg+disp]) の宛先は解決しない。その場合は 3 の vtable 表から間接的に辿る。
usage: splice_chain.py <pe> <hex_va> [...]
"""
import bisect
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
targets = [int(a, 16) for a in sys.argv[2:]]
tset = set(targets)


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


def rva_to_off(va):
    rva = va - IMG
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


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


rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
hits = {t: [] for t in targets}
md = Cs(CS_ARCH_X86, CS_MODE_64)
for ins in md.disasm(text.get_data(), t_base):
    if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
        try:
            tgt = int(ins.op_str, 16)
        except ValueError:
            tgt = None
        if tgt in tset:
            hits[tgt].append((ins.address, ins.mnemonic, "direct"))
    m = rip_re.search(ins.op_str)
    if m:
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        ea = ins.address + ins.size + d
        if ea in tset:
            hits[ea].append((ins.address, ins.mnemonic, "rip-operand"))

data_secs = [sec(b".rdata"), sec(b".data")]
slot8 = {t: [] for t in targets}
slot4 = {t: [] for t in targets}
rvas4 = {(t - IMG): t for t in targets}
for s in data_secs:
    raw = s.get_data()
    base = IMG + s.VirtualAddress
    for off in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, off)[0]
        if v in tset:
            slot8[v].append(base + off)
    for off in range(0, len(raw) - 3, 4):
        v = struct.unpack_from("<I", raw, off)[0]
        if v in rvas4:
            slot4[rvas4[v]].append(base + off)

for t in targets:
    foff = rva_to_off(t)
    print(f"== target {t:#x} (func start={func_of(t) == t}, file 0x{foff or 0:x})")
    for a, mn, kind in sorted(hits[t]):
        f = func_of(a)
        print(f"  code {a:#x} {mn:4s} [{kind}] in func {f:#x}" if f else f"  code {a:#x} {mn} [{kind}] in func ?")
    for s_va in slot8[t]:
        print(f"  slot8 {s_va:#x} (file 0x{rva_to_off(s_va) or 0:x})")
    for s_va in slot4[t]:
        print(f"  slot4-rva {s_va:#x} (file 0x{rva_to_off(s_va) or 0:x})")
