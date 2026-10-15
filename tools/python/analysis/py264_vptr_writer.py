#!/usr/bin/env python3
"""PY-264 (#3888): 0xed4b70 を呼ぶ仮想 call の receiver の vptr (0xed0c28) を書く箇所を PE で探す。

  FL_WIN64_DIR=<展開先> python3 analysis/py264_vptr_writer.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
出力: 各対象 VA の、生バイト列上の絶対値 (qword・dword)・RIP 相対参照の件数と場所。
"""
import os
import struct

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
VPTR = 0xED0C28
CELL = 0xED0B60
SLOT_OFF = 0x120
SLOT_TARGET = 0xED4B70
CALLEE_ENTRY = 0x11B2AC0
ENTRY_LEA = 0x1375A18


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase

    def find_all(pat):
        out, pos = [], raw.find(pat)
        while pos != -1:
            out.append(ib + pe.get_rva_from_offset(pos))
            pos = raw.find(pat, pos + 1)
        return out

    print("vtable check: [0x%x + 0x%x] = 0x%x (expect 0x%x)" % (
        VPTR, SLOT_OFF, struct.unpack("<Q", pe.get_data(VPTR + SLOT_OFF - ib, 8))[0], SLOT_TARGET))
    print("cell 0x%x value = 0x%x" % (CELL, struct.unpack("<Q", pe.get_data(CELL - ib, 8))[0]))
    for name, va in [("vptr 0x%x" % VPTR, VPTR), ("cell 0x%x" % CELL, CELL)]:
        print("%s qword hits: %s" % (name, [hex(x) for x in find_all(struct.pack("<Q", va))]))
        print("%s dword hits: %s" % (name, [hex(x) for x in find_all(struct.pack("<I", va))]))
    print("callee 0x%x qword hits: %s" % (CALLEE_ENTRY, [hex(x) for x in find_all(struct.pack("<Q", CALLEE_ENTRY))]))
    print("callee 0x%x dword hits: %s (.pdata RVA は除く)" % (
        CALLEE_ENTRY, [hex(x) for x in find_all(struct.pack("<I", CALLEE_ENTRY - ib))]))
    print("expected: lea at 0x%x -> 0x%x" % (ENTRY_LEA, CALLEE_ENTRY))


if __name__ == "__main__":
    main()
