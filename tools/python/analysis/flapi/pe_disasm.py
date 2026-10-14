#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の指定 VA から逆アセンブルする (PY-39 の解析補助。pe_handler_probe.py と同じ方式)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA(16進)> [命令数]

展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    va = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]
    rva = va - base
    fo = None
    for vaddr, vsz, praw, rsz in secs:
        if vaddr <= rva < vaddr + max(vsz, rsz):
            fo = praw + (rva - vaddr)
            break
    if fo is None:
        sys.exit("VA が section 外")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i, ins in enumerate(md.disasm(raw[fo:fo + count * 16], va)):
        if i >= count:
            break
        print(hex(ins.address), ins.mnemonic, ins.op_str)


if __name__ == "__main__":
    main()
