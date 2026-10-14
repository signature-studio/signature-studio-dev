#!/usr/bin/env python3
"""PY-160 (#3087): PE の .text 範囲を capstone で逆アセンブルする (実機不要)。

  python3 analysis/py160_dis.py <PE.bin> <lo_VA> <hi_VA>

例: python3 analysis/py160_dis.py work/py64/extracted/block00031_PE.bin 0xc61250 0xc612aa
"""
import sys

import capstone
import pefile


def main():
    path, lo, hi = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    with open(path, "rb") as f:
        data = f.read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off = text.PointerToRawData + (lo - base - text.VirtualAddress)
    for ins in md.disasm(data[off:off + (hi - lo)], lo):
        print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")


if __name__ == "__main__":
    main()
