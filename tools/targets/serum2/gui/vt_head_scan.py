#!/usr/bin/env python3
"""SR-100 #5986: vtable の中間スロットの VA から、その表の先頭 (head-8 に COL が来る位置) を後退探索し、RTTI クラス名を付ける (静的)。

vtable_dump.py は渡された VA を先頭と見なすため、中間スロットを渡すと RTTI=? になる。本ツールは先頭を探す。
入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: slot VA から 8 byte ずつ後退し、head-8 が COL (signature=1・TypeDescriptor 名が .?AV / .?AU で始まる) になる最初の位置を head とする。
      head から slot までの各値は vtable の関数アドレスである。
usage: vt_head_scan.py <pe> <slot_va_hex> [<slot_va_hex> ...] [--max-back 4096]
"""
import struct
import sys

import pefile

ARGS = sys.argv[1:]
MAX_BACK = int(ARGS[ARGS.index("--max-back") + 1]) if "--max-back" in ARGS else 4096
if "--max-back" in ARGS:
    i = ARGS.index("--max-back")
    del ARGS[i:i + 2]
PE_PATH = ARGS[0]
pe = pefile.PE(PE_PATH)
data = open(PE_PATH, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def rva_to_off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def read_q(va):
    return struct.unpack_from("<Q", data, rva_to_off(va - IMG))[0]


def rtti_of_col(col_va):
    off = rva_to_off(col_va - IMG)
    if off is None:
        return None
    sig, _offset, _cdoff, td_rva, _hier = struct.unpack_from("<IIIII", data, off)
    if sig != 1:
        return None
    off = rva_to_off(IMG + td_rva + 16 - IMG)
    if off is None:
        return None
    end = data.index(b"\0", off)
    name = data[off:end].decode(errors="replace")
    return name if name.startswith((".?AV", ".?AU")) else None


for arg in ARGS[1:]:
    slot = int(arg, 16)
    found = None
    for back in range(0, MAX_BACK // 8):
        head = slot - 8 * back
        col_va = read_q(head - 8)
        if IMG <= col_va < IMG + 0x10000000:
            name = rtti_of_col(col_va)
            if name:
                found = (head, col_va, name)
                break
    if found is None:
        print(f"slot {slot:#x}: 先頭が見つからない (max-back {MAX_BACK})")
        continue
    head, col_va, name = found
    print(f"slot {slot:#x}: head {head:#x} (index {(slot - head) // 8}) COL {col_va:#x} RTTI={name}")
