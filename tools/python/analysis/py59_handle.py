#!/usr/bin/env python3
"""PY-59 (#1974): .text 内の静的ハンドル H について、H-0x30 の関数ポインタと H-0x80 の dword (登録 ID) を出す (実機不要)。

  python3 analysis/py59_handle.py <PE.bin> <H VA hex> [<H VA hex> ...]

H-0x30 の関数 F を呼ぶと、H に対応する実体 (登録済みオブジェクト) が返る形の参照 (REPORT_PY59 §8)。
"""
import struct
import sys

import pefile


def main():
    path = sys.argv[1]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()

    def raw(va):
        rva = va - base
        for s in pe.sections:
            if s.PointerToRawData and s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"no raw data for {va:#x}")

    for arg in sys.argv[2:]:
        h = int(arg, 16)
        f = struct.unpack("<Q", data[raw(h - 0x30):raw(h - 0x30) + 8])[0]
        mid = struct.unpack("<i", data[raw(h - 0x80):raw(h - 0x80) + 4])[0]
        print(f"H {h:#x}: [H-0x30]={f:#x} ID=[H-0x80]={mid}")


if __name__ == "__main__":
    main()
