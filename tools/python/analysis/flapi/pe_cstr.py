#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の VA に置かれた C 文字列を読む (PY-119 の解析補助。pe_disasm.py と同じ方式)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_cstr.py <VA(16進)> [...]

REPORT_PY119_2977 の status → 文言の表 (0xd82c20 の lea rdx 先) を再現する。
"""
import os
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def v2o(va):
        rva = va - base
        for vaddr, vsz, praw, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return praw + (rva - vaddr)
        return None

    for arg in sys.argv[1:]:
        va = int(arg, 16)
        fo = v2o(va)
        end = raw.find(b"\0", fo, fo + 300) if fo is not None else -1
        text = raw[fo:end].decode("latin1") if end != -1 else None
        print(hex(va), repr(text))


if __name__ == "__main__":
    main()
