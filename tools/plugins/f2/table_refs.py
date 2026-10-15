#!/usr/bin/env python3
"""埋め込み関数表 (VA 範囲) の参照元を列挙する (#2574)。

使い方: python3 table_refs.py <block_PE.bin> <lo_hex> <hi_hex> [<slot_hex>]
出力:
- 範囲を含む pdata 関数、表の要素を (初期化, 破棄) の対として並べた一覧
- pdata 関数ごとの逆アセンブル: rip 相対・絶対 disp (index 付きを含む)・即値の参照。途中で止まった関数と未走査バイト数
- .text 全体の線形走査 (pdata の外の検算)。復号できなかったバイト数
- 表の各要素の VA (qword) と RVA (dword) を、ファイル全体の全オフセットで検索した結果
- slot_hex を与えたとき: slot への参照 (逆アセンブル・線形走査。w は書込み) と、slot を格納する qword・dword
"""
import bisect
import struct
import sys

import capstone
import pefile
from capstone import CS_AC_WRITE
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

CHUNK = 4096
NAMES = ["table", "slot"]


def refs_of(ins, targets):
    out = []
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            t, kind = ins.address + ins.size + op.mem.disp, "rip"
        elif op.type == X86_OP_MEM and op.mem.base == 0:
            t = op.mem.disp & 0xFFFFFFFFFFFFFFFF
            kind = "abs-idx" if op.mem.index else "abs"
        elif op.type == X86_OP_IMM:
            t, kind = op.imm & 0xFFFFFFFFFFFFFFFF, "imm"
        else:
            continue
        if op.type == X86_OP_MEM and op.access & CS_AC_WRITE:
            kind += "/w"
        for k, (lo, hi) in enumerate(targets):
            if lo <= t < hi:
                out.append((k, kind))
    return out


def pdata_pass(md, img, base, funcs, targets):
    hits, stops, unscanned = [], [], 0
    for b, e in funcs:
        end = b
        for ins in md.disasm(img[b - base:e - base + 16], b):
            if ins.address >= e:
                break
            end = ins.address + ins.size
            hits += [(ins.address, k, kind, ins.mnemonic, ins.op_str) for k, kind in refs_of(ins, targets)]
        if end < e:
            stops.append((b, e, e - end))
            unscanned += e - end
    return hits, stops, unscanned


def linear_pass(md, img, base, lo, hi, targets):
    hits, bad, a = [], 0, lo
    while a < hi:
        last = a
        for ins in md.disasm(img[a - base:min(a - base + CHUNK, hi - base)], a):
            last = ins.address + ins.size
            hits += [(ins.address, k, kind, ins.mnemonic, ins.op_str) for k, kind in refs_of(ins, targets)]
        if last == a:
            bad += 1
            a += 1
        else:
            a = last
    return hits, bad


def search(img, base, pat):
    out = []
    j = img.find(pat)
    while j != -1:
        out.append(hex(base + j))
        j = img.find(pat, j + 1)
    return out


def section(pe, name):
    return [s for s in pe.sections if s.Name.rstrip(b"\0") == name][0]


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    lo, hi = int(argv[2], 16), int(argv[3], 16)
    slot = int(argv[4], 16) if len(argv) == 5 else None
    targets = [(lo, hi)] + ([(slot, slot + 8)] if slot is not None else [])
    pd = section(pe, b".pdata")
    raw = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
    funcs = []
    for i in range(0, len(raw) - 11, 12):
        b, e, _ = struct.unpack_from("<III", raw, i)
        if b == 0:
            break
        funcs.append((base + b, base + e))
    funcs.sort()
    starts = [f[0] for f in funcs]

    def enclosing(a):
        i = bisect.bisect_right(starts, a) - 1
        return funcs[i] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None

    f = enclosing(lo)
    print(f"table {hex(lo)}..{hex(hi)} ({len(range(lo, hi, 8))} qword): enclosing pdata fn = {hex(f[0]) if f else None}")
    print("pairs (init, fini) as qword VA:")
    for va in range(lo, hi, 8):
        v = struct.unpack_from("<Q", img, va - base)[0]
        g = enclosing(v)
        print(f"  {hex(va)} -> {hex(v)} (pdata fn {hex(g[0]) if g else None})")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits, stops, unscanned = pdata_pass(md, img, base, funcs, targets)
    print(f"pdata 関数 {len(funcs)}: 逆アセンブルが途中で止まった関数 {len(stops)}、未走査 {unscanned} B")
    for b, e, n in stops:
        print(f"  stop fn {hex(b)}..{hex(e)} unscanned {n} B")
    print(f"code refs (pdata 関数内を逆アセンブル): {len(hits)}")
    for a, k, kind, m, s in sorted(hits):
        print(f"  {hex(a)} {NAMES[k]} {kind} {m} {s}")

    tx = section(pe, b".text")
    tlo = base + tx.VirtualAddress
    thi = tlo + tx.Misc_VirtualSize
    lhits, bad = linear_pass(md, img, base, tlo, thi, targets)
    print(f"線形走査 .text {hex(tlo)}..{hex(thi)}: 復号できなかった 1 バイト {bad} 件")
    print(f"code refs (線形走査): {len(lhits)}")
    for a, k, kind, m, s in sorted(lhits):
        print(f"  {hex(a)} {NAMES[k]} {kind} {m} {s}")

    qn = dn = 0
    print(f"表の要素 {len(range(lo, hi, 8))} 個の VA (qword) と RVA (dword)、全オフセット検索:")
    for va in range(lo, hi, 8):
        q = search(img, base, struct.pack("<Q", va))
        d = search(img, base, struct.pack("<I", va - base))
        qn += len(q)
        dn += len(d)
        print(f"  {hex(va)} qword {q} | RVA {hex(va - base)} dword {d}")
    print(f"element hits: qword {qn}, dword {dn}")
    v0 = struct.unpack_from("<Q", img, lo - base)[0]
    print(f"陽性対照: 要素 0 の値 {hex(v0)} の qword {search(img, base, struct.pack('<Q', v0))}、RVA の dword {search(img, base, struct.pack('<I', v0 - base))}")

    if slot is not None:
        print(f"slot {hex(slot)}: qword store {search(img, base, struct.pack('<Q', slot))}, dword RVA store {search(img, base, struct.pack('<I', slot - base))}")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        sys.exit(2)
    main(sys.argv)
