#!/usr/bin/env python3
"""FLEngine PE の全 section で、表 0xfe2c80・0xd14800・0xd147d0 を指す格納値を探す (#5191)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5191_qword.py

pe_py5191_table_readers.py が命令のオペランドだけを見るのに対し、こちらはデータ領域の格納値を見る。
表の基底を読み出して加算する経路では、基底の値が 8 byte (絶対 VA) か 4 byte (RVA・相対オフセット)
のどちらかで格納されるため、両方を照合する。
"""
import os
import struct

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
TARGETS = {0xFE2C80: "table_base", 0xD14800: "d14800", 0xD147D0: "d147d0",
           0xFFF070: "control_fff070"}


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    print(f"ImageBase=0x{base:x}")
    hits = 0
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        for off in range(0, len(data) - 7, 4):
            q = struct.unpack_from("<Q", data, off)[0] if off + 8 <= len(data) else None
            d = struct.unpack_from("<I", data, off)[0]
            va = base + s.VirtualAddress + off
            for tgt, label in TARGETS.items():
                if q is not None and (q == base + tgt or q == tgt):
                    hits += 1
                    print(f"{name:8s} q8 va=0x{va:x} value=0x{q:x} ({label})")
                if d == tgt or d == tgt - base:
                    hits += 1
                    print(f"{name:8s} d4 va=0x{va:x} value=0x{d:x} ({label})")
    print(f"hits={hits}")


if __name__ == "__main__":
    main()
