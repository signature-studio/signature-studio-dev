#!/usr/bin/env python3
"""ks_fa75_delay_map.py <HeartCore.core_64> <SlateCore.core_64> — KH/SC Delay の param 読み出しを検査する (#5451 / FA-75)

判定: 下の期待値 (逆アセンブルで確認した命令・定数) が素材の機械語と一致するかを見る。
意味ラベルは出さない (機械語の構造からの読みは REPORT 側に書く)。
"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

KH_FN, KH_LEN = 0x1802ED7F0, 3291
SC_FN, SC_LEN = 0x180BA8AD0, 2551
KH_TABLE_RIP_INS = 0x1802ED8FC  # lea r9,[rip+disp] (6 要素の分数表)
KH_P_OFFS = [0x0, 0x4, 0x8, 0xC, 0x10, 0x18, 0x1C, 0x20]
SC_P_OFFS = [0x9EE4, 0x9F38, 0x9F74, 0x9FBC, 0xA004]


def disasm(pe, va, size):
    base = pe.OPTIONAL_HEADER.ImageBase
    code = pe.get_data(va - base, size)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    return list(md.disasm(code, va))


def has_load(insns, base_reg, off):
    pat = re.compile(r"\[%s(?: \+ (?:0x)?%x)?\]" % (base_reg, off) if off else r"\[%s\]" % base_reg)
    return any(pat.search(i.op_str) for i in insns)


def main():
    kh = pefile.PE(sys.argv[1])
    sc = pefile.PE(sys.argv[2])
    kh_i = disasm(kh, KH_FN, KH_LEN)
    sc_i = disasm(sc, SC_FN, SC_LEN)
    ok = True

    for off in KH_P_OFFS:
        hit = has_load(kh_i, "rax", off) or has_load(kh_i, "rbx", off) or has_load(kh_i, "rdx", off)
        print("%s KH P+0x%x" % ("OK" if hit else "NG", off))
        ok &= hit

    for va in SC_P_OFFS:
        hit = has_load(sc_i, "rax", va)
        print("%s SC P+0x%x" % ("OK" if hit else "NG", va))
        ok &= hit

    ins = [i for i in kh_i if i.address == KH_TABLE_RIP_INS]
    if ins:
        i = ins[0]
        disp = int(i.op_str.split("+")[1].split("]")[0], 16)
        tab = i.address + i.size + disp
        data = kh.get_data(tab - kh.OPTIONAL_HEADER.ImageBase, 48)
        vals = [struct.unpack("<d", data[k * 8:k * 8 + 8])[0] for k in range(6)]
        exp = [2 / 3, 1 / 2, 1 / 3, 1 / 4, 1 / 6, 1 / 8]
        good = all(abs(a - b) < 1e-15 for a, b in zip(vals, exp))
        print("%s KH table 0x%x = %s" % ("OK" if good else "NG", tab, ", ".join("%.6g" % v for v in vals)))
        ok &= good
    else:
        print("NG KH table: lea @0x%x not found" % KH_TABLE_RIP_INS)
        ok = False

    fb = [
        (0x1802ED930, "movss", "xmm12, dword ptr [rax + 0x10]"),
        (0x1802EDA8A, "movss", "dword ptr [rdi + 0xb8], xmm12"),
        (0x1802EE127, "movss", "xmm2, dword ptr [rdi + 0xb0]"),
        (0x1802EE12F, "movss", "xmm3, dword ptr [rdi + 0xb4]"),
        (0x1802EE143, "movss", "dword ptr [rdi + 0xb8], xmm3"),
        (0x1802EE2A1, "movq", "xmm0, xmm1"),
        (0x1802EE2C7, "movups", "xmm3, xmmword ptr [rdi + 0xb8]"),
        (0x1802EE2D2, "mulps", "xmm3, xmm0"),
        (0x1802EE2D5, "addps", "xmm3, xmm2"),
        (0x1802EE3B3, "movups", "xmm3, xmmword ptr [rdi + 0xb8]"),
        (0x1802EE3BE, "mulps", "xmm3, xmm0"),
        (0x1802EE4C1, "movss", "dword ptr [rdx + rax*4], xmm3"),
        (0x1802EE2B6, "test", "bpl, 1"),
        (0x1802EE2C0, "shufps", "xmm2, xmm2, 0xe1"),
    ]
    by_va = {i.address: i for i in kh_i}
    for va, mn, ops in fb:
        i = by_va.get(va)
        hit = i is not None and i.mnemonic == mn and i.op_str == ops
        print("%s KH feedback @0x%x %s %s" % ("OK" if hit else "NG", va, mn, ops))
        ok &= hit

    print("OK: Delay param 読み出しの検査 (意味ラベルは未確定)" if ok else "NG: 検査に失敗")
    print("EXIT=%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
