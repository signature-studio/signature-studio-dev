#!/usr/bin/env python3
"""PY-5144 (#5144): 群 C の 2 サイトの受け手 (Self のフィールド) の書込み元を確認する。

  python3 analysis/py5144_groupc.py <PE.bin>

対象 (REPORT_PY86.md §2 の群 C):
  0xb35298 (fn 0xb35250・所属 VMT TDBXStreamValue 0xb07378): 受け手 = [Self+0x18]
  0xb671a2 (fn 0xb67190・所属 VMT TGenericPlugin 0xb655c8): 受け手 = [Self+0x7a0]

方法:
1. 対象クラスの VMT の全スロットの関数 (= そのクラスのメソッド) を集める。
   VMT の後ろのスロットを、.text の範囲に入る間だけ読む。
2. 各メソッドの中で、Self (rbx/rcx/rsi/rdi 等の最初の引数の保存先は不確実のため、
   `[reg+disp]` 形式で reg が rbx/rsi/rdi/r12〜r15 のものを候補) へ書く mov を集め、書込み元の直前 3 命令を出す。
3. 対象 fn への直接 call rel32 の呼出し元を出す。
"""
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tlo = text.PointerToRawData
tdata = data[tlo:tlo + text.SizeOfRawData]
tbase = ib + text.VirtualAddress
tend = tbase + text.SizeOfRawData


def va_to_off(va):
    for s in pe.sections:
        lo = ib + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return va - lo + s.PointerToRawData
    return None


def u64(va):
    off = va_to_off(va)
    return None if off is None else int.from_bytes(data[off:off + 8], "little")


def shortstr(va):
    off = va_to_off(va)
    return data[off + 1:off + 1 + data[off]].decode("latin-1")


def owners(fn):
    out = []
    pat = int.to_bytes(fn, 8, "little")
    pos = data.find(pat)
    while pos >= 0:
        hva = None
        for s in pe.sections:
            if s.PointerToRawData <= pos < s.PointerToRawData + s.SizeOfRawData:
                hva = ib + s.VirtualAddress + (pos - s.PointerToRawData)
        if hva is not None:
            for k in range(0, 0x400, 8):
                b = hva - k
                if u64(b - 0xC8) == b:
                    ti = u64(b - 0xA8)
                    name = shortstr(ti + 1) if ti and va_to_off(ti) is not None else None
                    out.append((name, b))
                    break
        pos = data.find(pat, pos + 1)
    return out


def vmt_methods(vmt):
    """VMT の各スロットのうち .text 内を指すものを返す。"""
    res = []
    for k in range(0, 0x800, 8):
        v = u64(vmt + k)
        if v is None:
            break
        if not (tbase <= v < tend):
            if k > 0x100:
                break
            continue
        res.append((k // 8, v))
    return res


TARGETS = [
    (0xb35250, 0x18, "TDBXStreamValue"),
    (0xb67190, 0x7a0, "TGenericPlugin"),
]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
SELF_REGS = None

for fn, disp, cls in TARGETS:
    own = [b for n, b in owners(fn) if n == cls]
    print(f"== 対象 fn {fn:#x} (所属 {cls} VMT {[hex(b) for b in own]}) 受け手 = Self+{disp:#x}")
    if not own:
        continue
    vmt = own[0]
    methods = vmt_methods(vmt)
    print(f"  VMT {vmt:#x} の .text スロット {len(methods)} 件")
    cs = []
    for m in range(0, len(tdata) - 5):
        if tdata[m] == 0xE8:
            rel = int.from_bytes(tdata[m + 1:m + 5], "little", signed=True)
            if tbase + m + 5 + rel == fn:
                cs.append(tbase + m)
    print(f"  fn {fn:#x} への直接 call rel32: {len(cs)} 件 {[hex(c) for c in cs[:8]]}")
    for slot, mf in methods:
        s = mf - tbase
        e = tdata.find(b"\xCC", s)
        if e < 0:
            e = len(tdata)
        body = tdata[s:e]
        ins_list = list(md.disasm(body, mf))
        hits = []
        for idx, ins in enumerate(ins_list):
            if ins.mnemonic != "mov" or len(ins.operands) != 2:
                continue
            d = ins.operands[0]
            if (d.type == X.X86_OP_MEM and d.mem.index == 0 and d.mem.disp == disp
                    and d.mem.base not in (X.X86_REG_RIP, X.X86_REG_RSP, X.X86_REG_RBP, 0)):
                hits.append(idx)
        if not hits:
            continue
        print(f"  slot[{slot}] fn {mf:#x}: Self+{disp:#x} 書込み {len(hits)} 件")
        for idx in hits:
            for i in ins_list[max(0, idx - 3):idx + 1]:
                print(f"      {i.address:#x}: {i.mnemonic} {i.op_str}")
            print("      ---")
