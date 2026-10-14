#!/usr/bin/env python3
"""PY-71 (#2501): VMT の親鎖を辿る (実機不要)。

  python3 analysis/py71_chain.py <PE.bin> <VMT VA hex>[,<VMT VA hex>...]

VMT-0x78 の値 (親 VMT のポインタを格納した位置) を読み、その位置の値を親 VMT とみなす。
TypeInfo 名が TObject になるか、読めなくなるまで繰り返す。py71_vmt.py と同じ配置を仮定する。
"""
import sys

import pefile

path = sys.argv[1]
pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase


def va_to_off(va):
    for s in pe.sections:
        lo = ib + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return va - lo + s.PointerToRawData
    return None


def u64(va):
    off = va_to_off(va)
    return None if off is None else int.from_bytes(data[off:off + 8], "little")


def class_name(vmt):
    ti = u64(vmt - 0xA8)
    off = None if ti is None else va_to_off(ti + 1)
    if off is None:
        return None
    return data[off + 1:off + 1 + data[off]].decode("latin-1")


for start in sys.argv[2].split(","):
    cur = int(start, 0)
    chain = []
    for _ in range(30):
        name = class_name(cur)
        chain.append(f"{name} {cur:#x}")
        if name == "TObject":
            break
        store = u64(cur - 0x78)
        parent = u64(store) if store else None
        if not parent:
            chain.append("(読めず)")
            break
        cur = parent
    print(" -> ".join(chain))
