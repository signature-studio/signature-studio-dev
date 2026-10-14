#!/usr/bin/env python3
"""PY-55 (#1916): FLEngine PE 上で指定 displacement へ書き込む mov 命令を列挙する (実機不要)。

  python3 analysis/py55_fieldwrites.py <PE.bin> <disp hex> [<disp hex> ...]

disp32 のリトルエンディアン列を .text 全域から検索する。ヒット位置 pos に対して、
開始位置 pos-back (back = 1..11) から復号し、開始位置が命令境界で disp の 4 バイトを
完全に含む命令を採用する。メモリ先頭オペランドが [.. + disp] の mov (書込み) だけを出す。
"""
import sys

import capstone
import pefile


def insn_containing(md, tdata, tbase, pos, width=4):
    found = []
    for back in range(1, 12):
        start = pos - back
        if start < 0:
            continue
        for ins in md.disasm(tdata[start:start + 16], tbase + start):
            if ins.address != tbase + start:
                break
            if ins.address == tbase + start and ins.size >= back + width:
                found.append((back, ins))
            break
    return found


def main():
    path = sys.argv[1]
    disps = [int(v, 16) for v in sys.argv[2:]]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    tbase = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for disp in disps:
        needle = f"+ {disp:#x}]"
        pat = disp.to_bytes(4, "little")
        print(f"== disp {disp:#x} ==")
        pos = tdata.find(pat)
        while pos != -1:
            for back, ins in insn_containing(md, tdata, tbase, pos):
                if ins.mnemonic == "mov":
                    first = ins.op_str.split(",")[0]
                    if "[" in first and needle in first:
                        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
            pos = tdata.find(pat, pos + 1)
        print()


if __name__ == "__main__":
    main()
