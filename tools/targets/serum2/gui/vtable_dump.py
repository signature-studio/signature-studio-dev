#!/usr/bin/env python3
"""SR-30 #2000: vtable head VA から先頭 N スロットを出し、MSVC RTTI のクラス名 (COL 経由) を付ける。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: vtable head の直前 8 byte が COL (Complete Object Locator) への RVA ではなく
      ポインタ (x64 では COL の VA) になっている場合は COL の pTypeDescriptor を辿る。
      x64 MSVC では COL の signature=1 のとき各種 offset は 32bit RVA。
usage: vtable_dump.py <pe> <vtable_head_hex> [<n_slots>]
"""
import struct
import sys

import pefile

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
head = int(sys.argv[2], 16)
n = int(sys.argv[3]) if len(sys.argv) > 3 else 8


def rva_to_off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def read_q(va):
    off = rva_to_off(va - IMG)
    return struct.unpack_from("<Q", data, off)[0]


def read_u32(va):
    off = rva_to_off(va - IMG)
    return struct.unpack_from("<I", data, off)[0]


def cstr(va):
    off = rva_to_off(va - IMG)
    end = data.index(b"\0", off)
    return data[off:end].decode(errors="replace")


col_va = read_q(head - 8)
type_name = "?"
if IMG <= col_va < IMG + 0x10000000:
    col_off = rva_to_off(col_va - IMG)
    sig, offset, cdoff, td_rva, hier_rva = struct.unpack_from("<IIIII", data, col_off)
    if sig == 1:
        td_va = IMG + td_rva
        # TypeDescriptor: vfptr(8) spare(8) name[]
        type_name = cstr(td_va + 16)
print(f"vtable head {head:#x} RTTI={type_name}")
for i in range(n):
    v = read_q(head + 8 * i)
    print(f"  slot {i:2d} @ {head + 8 * i:#x} = {v:#x}")
