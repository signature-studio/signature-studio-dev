#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の指定 VA から N 命令を逆アセし、RIP 相対で参照するデータの値を出す (PY-75 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_consts.py <VA(16進)> [命令数]

各行: 命令の VA・命令・参照先 VA・参照先の 8 byte (qword) と 4 byte (float として解釈した値)。
参照先が .data/.bss の場合、PE ファイル上の値は 0 (実行時に初期化される) で、ここでは読めない。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def main():
    va = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def read(addr, n):
        rva = addr - base
        for vaddr, vsz, praw, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                fo = praw + (rva - vaddr)
                return raw[fo:fo + n]
        return None

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
        line = "%s %s %s" % (hex(ins.address), ins.mnemonic, ins.op_str)
        m = RIP.search(ins.op_str)
        if m:
            disp = int(m.group(2), 16) * (-1 if m.group(1) == "-" else 1)
            target = ins.address + ins.size + disp
            data = read(target, 8)
            if data is None:
                line += "  -> %s (section 外)" % hex(target)
            else:
                q = struct.unpack("<Q", data)[0]
                f = struct.unpack("<f", data[:4])[0]
                line += "  -> %s qword=%s float=%r" % (hex(target), hex(q), f)
        print(line)


if __name__ == "__main__":
    main()
