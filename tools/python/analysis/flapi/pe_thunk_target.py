#!/usr/bin/env python3
"""FLEngine PE の `jmp qword ptr [rip+disp]` 形の thunk (間接 jmp) の飛び先 VA を読む (PY-4852 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_thunk_target.py <VA(16進)> [<VA(16進)> ...]

展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    raw = open(PE, "rb").read()

    def rva_to_off(rva):
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        return None

    for arg in sys.argv[1:]:
        va = int(arg, 16)
        off = rva_to_off(va - base)
        if off is None or raw[off:off + 2] != b"\xff\x25":
            print(hex(va), "not a jmp-indirect thunk")
            continue
        disp = struct.unpack("<i", raw[off + 2:off + 6])[0]
        slot_va = va + 6 + disp
        target = struct.unpack("<Q", raw[rva_to_off(slot_va - base):][:8])[0]
        print(hex(va), "slot", hex(slot_va), "target", hex(target))


if __name__ == "__main__":
    main()
