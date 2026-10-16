#!/usr/bin/env python3
"""hs_disp_callers.py — FLE TFruityHost.Dispatcher (0x13173a0) への直接 call/jmp (E8/E9 rel32) を列挙する (#5663)。

直接呼出元が 0 件なら、Dispatcher は vtable 経由 (間接) でしか呼ばれない。
全 .text を線形に走査し、E8/E9 の rel32 が 0x13173a0 を指すものを出す。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<pefile 入り lib> python3 hs_disp_callers.py
"""
import os
import sys
import struct

import pefile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
DISP = 0x13173a0


def main():
    pe = pefile.PE(PE_PATH, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    hits = []
    for sec in pe.sections:
        if not (sec.Characteristics & 0x20000000):
            continue
        data = image[sec.VirtualAddress:sec.VirtualAddress + sec.Misc_VirtualSize]
        for i in range(len(data) - 5):
            if data[i] in (0xE8, 0xE9):
                rel = struct.unpack_from('<i', data, i + 1)[0]
                if base + sec.VirtualAddress + i + 5 + rel == DISP:
                    hits.append(base + sec.VirtualAddress + i)
    print(f'direct E8/E9 to 0x{DISP:x}: {len(hits)} sites')
    for va in hits:
        print(f'  0x{va:x}')


if __name__ == '__main__':
    main()
