#!/usr/bin/env python3
"""埋め込み関数表 (VA 範囲) の参照元を、pdata 関数ごとの逆アセンブルで列挙する (#2574)。

使い方: python3 table_refs.py <block_PE.bin> <lo_hex> <hi_hex>
出力: 範囲を含む pdata 関数、表の要素を (初期化, 破棄) の対として並べた一覧、
rip 相対参照・絶対 disp (index 付きを含む)・即値、qword 格納 (VA)、dword 格納 (RVA) を出す。
fn_refs.py と違い、絶対 disp の index 付き参照と dword RVA 格納を見る。線形走査ではなく関数単位で逆アセンブルする。
"""
import bisect
import struct
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    lo, hi = int(argv[2], 16), int(argv[3], 16)
    pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
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
    hits = []
    for b, e in funcs:
        for ins in md.disasm(img[b - base:e - base + 16], b):
            if ins.address >= e:
                break
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                    if lo <= t < hi:
                        hits.append((ins.address, "rip", ins.mnemonic, ins.op_str))
                elif op.type == X86_OP_MEM and op.mem.base == 0:
                    d = op.mem.disp & 0xFFFFFFFFFFFFFFFF
                    if lo <= d < hi:
                        hits.append((ins.address, "abs-idx" if op.mem.index else "abs", ins.mnemonic, ins.op_str))
                elif op.type == X86_OP_IMM and lo <= (op.imm & 0xFFFFFFFFFFFFFFFF) < hi:
                    hits.append((ins.address, "imm", ins.mnemonic, ins.op_str))
    print(f"code refs (pdata 関数内を逆アセンブル): {len(hits)}")
    for a, k, m, s in sorted(hits):
        print(f"  {hex(a)} {k} {m} {s}")

    qs = []
    j = img.find(struct.pack("<Q", lo))
    while j != -1:
        qs.append(hex(base + j))
        j = img.find(struct.pack("<Q", lo), j + 1)
    print(f"qword store of table VA {hex(lo)}: {qs}")
    ds = []
    j = img.find(struct.pack("<I", lo - base))
    while j != -1:
        ds.append(hex(base + j))
        j = img.find(struct.pack("<I", lo - base), j + 1)
    print(f"dword RVA store of table {hex(lo - base)}: {ds}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv)
