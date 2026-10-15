#!/usr/bin/env python3
"""PY-264 (#3888): 大域セル 0x15e0f78 を RIP 相対で読む箇所の直後 8 命令を逆アセンブルする。

  FL_WIN64_DIR=<展開先> python3 analysis/py264_cell_callers.py <参照 VA (16進)> ...

引数には analysis/flapi/pe_rip_refs.py 0x15e0f78 の出力の番地を渡す。
各番地から 64 byte を逆アセンブルし、先頭 8 命令を出す。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
SPAN = 8


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for arg in sys.argv[1:]:
        va = int(arg, 16)
        code = pe.get_data(va - ib, 64)
        window = list(md.disasm(code, va))[:SPAN]
        print("0x%x  ->  %s" % (va, " ; ".join("%s %s" % (i.mnemonic, i.op_str) for i in window)))


if __name__ == "__main__":
    main()
