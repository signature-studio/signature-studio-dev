#!/usr/bin/env python3
"""PY-59 (#1974): 指定 VA を呼ぶ call rel32 (E8) と jmp rel32 (E9) の位置を列挙する (実機不要)。

  python3 analysis/py59_callers.py <PE.bin> <target VA hex>
"""
import sys

import pefile


def main():
    path = sys.argv[1]
    target = int(sys.argv[2], 16)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        sbase = base + s.VirtualAddress
        for opc in (0xE8, 0xE9):
            pat = bytes([opc])
            pos = raw.find(pat)
            while pos != -1:
                if pos + 5 <= len(raw):
                    rel = int.from_bytes(raw[pos + 1:pos + 5], "little", signed=True)
                    if sbase + pos + 5 + rel == target:
                        print(f"{sbase + pos:#x}: {'call' if opc == 0xE8 else 'jmp'}")
                pos = raw.find(pat, pos + 1)


if __name__ == "__main__":
    main()
