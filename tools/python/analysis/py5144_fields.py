#!/usr/bin/env python3
"""PY-5144 (#5144): Delphi x64 の FieldTable (VMT-48) から宣言フィールドを引く。

  python3 analysis/py5144_fields.py <PE.bin> <VMT_VA_hex> [<VMT_VA_hex> ...]

Delphi の TFieldTable (packed): ClassTab(8) / Count(WORD) / FieldInfo[Count]。
TFieldInfo (packed): FieldOffset(u32) / TypeIndex(u16) / Name(ShortString)。
検証: ClassName が読めること・Count が妥当であること・各 FieldOffset が InstanceSize 未満で、
Name が識別子であること。check が NG の行は採らないこと。
"""
import re
import struct
import sys

import pefile

path = sys.argv[1]
vmts = [int(v, 16) for v in sys.argv[2:]]
pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
IDENT = re.compile(rb"^[A-Za-z_][A-Za-z0-9_]*$")


def rd(va, n):
    return data[pe.get_offset_from_rva(va - ib):][:n]


def q(va):
    return struct.unpack("<Q", rd(va, 8))[0]


def pstr(va):
    b = rd(va, 256)
    return b[1:1 + b[0]]


for vmt in vmts:
    cname = pstr(q(vmt - 24))
    isz = q(vmt - 16)
    ft = q(vmt - 48)
    print(f"VMT {vmt:#x} ClassName={cname.decode('latin1')} InstanceSize={isz}")
    if ft == 0:
        print("  FieldTable: nil")
        continue
    count = struct.unpack("<H", rd(ft + 8, 2))[0]
    ok = 0 <= count < 1024 and 0 < isz < 0x100000
    print(f"  FieldTable {ft:#x} Count={count} check={'ok' if ok else 'NG'}")
    if not ok:
        continue
    entry = ft + 10
    for i in range(count):
        off = struct.unpack("<I", rd(entry, 4))[0]
        tidx = struct.unpack("<H", rd(entry + 4, 2))[0]
        nm = pstr(entry + 6)
        valid = off < isz and IDENT.match(nm) is not None
        print(
            f"  [{i:02d}] +{off:#x} typeidx={tidx} name={nm.decode('latin1')!r}"
            f" check={'ok' if valid else 'NG'}"
        )
        entry += 6 + 1 + len(nm)
