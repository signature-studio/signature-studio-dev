#!/usr/bin/env python3
"""PY-403 (#4921): G1 (0x15d51a0) への書込み 12 件と、関数 0x12d94f0 の loop の前後の逆アセンブルを出す。

  FL_WIN64_DIR=<展開先> python3 analysis/py403_g1_write_context.py [before] [after]

出力: 各書込みの直前 before 命令 (既定 6)・書込み命令・後 after 命令 (既定 1)。
loop 関数 0x12d94f0 と述語 0x12d8d30 は別表で出す。分岐条件の解釈は REPORT 側で行う (本スクリプトは読むだけ)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G1 = 0x15D51A0

WRITES = [
    0xC4EFE0, 0xC4F418, 0xDCDE4B, 0xF42909, 0xF48425, 0xF48454,
    0x10467B4, 0x10467DD, 0x1071C34, 0x1071C85, 0x12C9343, 0x12C935E,
]
LOOP_FN = (0x12D94F0, 0x12D9680)
PRED_FN = (0x12D8D30, 0x12D8DB2)


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    return raw, pe, base, md


def read(raw, pe, base, va, n):
    rva = va - base
    for s in pe.sections:
        size = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if s.VirtualAddress <= rva < s.VirtualAddress + size:
            off = s.PointerToRawData + (rva - s.VirtualAddress)
            return raw[off:off + n]
    raise ValueError(hex(va))


def disasm(md, raw, pe, base, start, end):
    code = read(raw, pe, base, start, end - start + 16)
    return [i for i in md.disasm(code, start) if i.address < end]


def main():
    before = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    after = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    raw, pe, base, md = load()
    for w in WRITES:
        seq = []
        for back in range(0x40, 0x0, -1):
            seq = disasm(md, raw, pe, base, w - back, w + 16)
            if any(i.address == w for i in seq):
                break
        idx = next(k for k, i in enumerate(seq) if i.address == w)
        print(f"## write {w:#x}")
        for i in seq[max(0, idx - before):idx + after + 1]:
            mark = ">" if i.address == w else " "
            print(f"{mark} {i.address:#x}: {i.mnemonic} {i.op_str}")
        print()
    for name, (s, e) in [("loop 0x12d94f0", LOOP_FN), ("pred 0x12d8d30", PRED_FN)]:
        print(f"## {name}")
        for i in disasm(md, raw, pe, base, s, e):
            print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
        print()


if __name__ == "__main__":
    main()
