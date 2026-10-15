#!/usr/bin/env python3
"""PY-86 (#2701): VMT のスロットを間接 call する各サイトの受け手の出所を並べる (実機不要・近似)。

  python3 analysis/py86_slot52.py <PE.bin> <slot disp hex> [max callers]

1. .text を 1 回線形走査し、`call qword ptr [reg + disp]` のサイトと、直接 call (rel) の呼出し先を集める
   (py71_slotcallers.py と同じ近似: int3 パディングの直後の命令を関数先頭とみなす)。
2. 各サイトについて次を出す。
   - 所属関数 fn の先頭から呼出しまでの命令 (受け手のレジスタの最後の書込みを読む)
   - fn の値を仮想メソッドとして持つ VMT (クラス名・スロット番号)。VMT は自己ポインタ (VMT-0xc8) で判定する
   - fn の直接の呼出し元と、その呼出し元の VMT 所属
3. 正の対照: 既知の VMT スロット値 (TPublicChannel の +0x1a0 = 0xffe370・TChannel の +0x1a0 = 0xfed770) が、
   それぞれのクラスの所属として引けるかを先頭で出す。
"""
import collections
import struct
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
slot = int(sys.argv[2], 0)
max_callers = int(sys.argv[3]) if len(sys.argv) > 3 else 6

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
    """fn の値を VMT のスロットに持つ VMT を (クラス名, VMT, スロット番号) で返す。"""
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


def fmt_owners(fn):
    return ", ".join(f"{n}@{b:#x}[{i}]" for n, b, i in owners(fn)) or "-"


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
sites = []
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
    if ins.mnemonic != "call":
        continue
    op = ins.operands[0]
    if op.type == X.X86_OP_IMM:
        calls_to[op.imm].add(fn)
    elif (op.type == X.X86_OP_MEM and op.mem.base not in (X.X86_REG_RIP, X.X86_REG_RBP, X.X86_REG_RSP, 0)
          and op.mem.index == 0 and op.mem.disp == slot):
        sites.append((ins.address, fn, ins.reg_name(op.mem.base)))

print(f"# slot disp {slot:#x}: 呼出しサイト {len(sites)} 件 / 直接 call の呼出し先 {len(calls_to)} 種")
print("# 正の対照 (VMT 所属):")
print(f"#   0xffe370 -> {fmt_owners(0xffe370)}")
print(f"#   0xfed770 -> {fmt_owners(0xfed770)}")
print()

for addr, f, reg in sites:
    print(f"== call@{addr:#x} fn={f:#x} reg={reg}")
    print(f"  owners(fn) = {fmt_owners(f)}")
    cs = sorted(calls_to.get(f, ()))
    print(f"  direct callers = {len(cs)}")
    for c in cs[:max_callers]:
        print(f"    <- {c:#x}  owners={fmt_owners(c)}")
    body = []
    for ins in md.disasm(data[va_to_off(f):va_to_off(addr)], f):
        body.append(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    print("  tail:")
    for line in body[-12:]:
        print(f"    {line}")
    print(f"    {addr:#x}: call [{reg}+{slot:#x}]")
