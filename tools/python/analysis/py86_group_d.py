#!/usr/bin/env python3
"""PY-86 群 D (#5145): VMT 外の関数を直接呼出し元へ辿り、受け手の所属 VMT を並べる (実機不要・近似)。

  python3 analysis/py86_group_d.py <PE.bin> <fn hex,fn hex,...> [depth] [max callers]

1. py86_slot52.py と同じ線形走査で、rel32 の直接 call を (呼出しサイト, 呼出し元 fn) として集める。
2. 各 fn について、VMT 所属の関数に当たるまで直接呼出し元を depth 段まで辿る。
   VMT 所属の関数で止める (その関数の所属クラスが受け手の型の候補になる)。
"""
import collections
import struct
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
fns = [int(x, 16) for x in sys.argv[2].split(",")]
depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
max_callers = int(sys.argv[4]) if len(sys.argv) > 4 else 6

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = ib + text.VirtualAddress


def va_to_off(va):
    for s in pe.sections:
        lo = ib + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return va - lo + s.PointerToRawData
    return None


def off_to_va(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return ib + s.VirtualAddress + (off - s.PointerToRawData)
    return None


def u64(va):
    off = va_to_off(va)
    return None if off is None else int.from_bytes(data[off:off + 8], "little")


def shortstr(va):
    off = va_to_off(va)
    if off is None:
        return None
    n = data[off]
    return data[off + 1:off + 1 + n].decode("latin-1")


def class_name(vmt):
    ti = u64(vmt - 0xA8)
    if ti is None or va_to_off(ti) is None:
        return None
    return shortstr(ti + 1)


def owners(fn):
    out = []
    pat = struct.pack("<Q", fn)
    pos = data.find(pat)
    while pos >= 0:
        hva = off_to_va(pos)
        if hva is not None:
            for k in range(0, 0x400, 8):
                b = hva - k
                if u64(b - 0xC8) == b:
                    out.append((class_name(b), b, k // 8))
                    break
        pos = data.find(pat, pos + 1)
    return out


def fmt_owners(fn, limit=3):
    o = owners(fn)
    if not o:
        return "-"
    head = ", ".join(f"{n}@{b:#x}[{i}]" for n, b, i in o[:limit])
    return head + (f" 他 {len(o) - limit} 件" if len(o) > limit else "")


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
calls_to = collections.defaultdict(set)
fn = None
pad = True
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        pad = True
        continue
    off += ins.size
    if ins.mnemonic == "int3":
        pad = True
        continue
    if pad:
        fn = ins.address
        pad = False
    if ins.mnemonic == "call" and ins.operands[0].type == X.X86_OP_IMM:
        calls_to[ins.operands[0].imm].add((ins.address, fn))


def walk(f, d, indent, seen):
    names = [n for n, _, _ in owners(f)]
    tpc = "TPublicChannel" in names
    print(f"{indent}{f:#x} owners={fmt_owners(f)} TPublicChannel={'有' if tpc else '無'} callers={len(calls_to.get(f, ()))}")
    if owners(f) or d == 0 or f in seen:
        return
    seen.add(f)
    sites = sorted(calls_to.get(f, ()), key=lambda t: t[1])
    for site, c in sites[:max_callers]:
        print(f"{indent}  <- call@{site:#x} in {c:#x}")
        walk(c, d - 1, indent + "    ", seen)


for f in fns:
    print(f"== fn {f:#x}")
    walk(f, depth, "  ", set())
