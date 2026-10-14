#!/usr/bin/env python3
"""指定 VA から n 命令の RIP 相対オペランドを解決し、スロットの値 (f32/f64) と、スロットがポインタなら指す先の値を出す (PY-72 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_consts.py <VA(16進)> [命令数]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def read_va(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                if rva - s.VirtualAddress >= s.SizeOfRawData:
                    return None
                fo = s.PointerToRawData + (rva - s.VirtualAddress)
                return raw[fo:fo + n]
        return None

    start = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = read_va(start, count * 16)
    for i, ins in enumerate(md.disasm(code, start)):
        if i >= count:
            break
        m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", ins.op_str)
        if not m:
            continue
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        slot = ins.address + ins.size + d
        line = f"{hex(ins.address)} {ins.mnemonic} {ins.op_str} -> slot {hex(slot)}"
        b = read_va(slot, 8)
        if b is None:
            print(line + " [PE ファイル上に実体なし]")
            continue
        line += f" f32={struct.unpack('<f', b[:4])[0]!r} f64={struct.unpack('<d', b)[0]!r}"
        p = struct.unpack("<Q", b)[0]
        if base <= p < base + 0x10000000:
            pb = read_va(p, 8)
            if pb:
                line += f" | *ptr={p:#x} f32={struct.unpack('<f', pb[:4])[0]!r} f64={struct.unpack('<d', pb)[0]!r}"
        print(line)


if __name__ == "__main__":
    main()
