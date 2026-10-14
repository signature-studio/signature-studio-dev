#!/usr/bin/env python3
"""PY-71 (#2501): VMT (仮想メソッドテーブル) の先頭に付く RTTI ヘッダを読み、クラス名を確かめる (実機不要)。

  python3 analysis/py71_vmt.py <PE.bin> <VMT VA hex>[,<VMT VA hex>...] [slot disp hex]

slot disp を付けると、各 VMT の VMT+disp (仮想メソッドのスロット値) も出す。

VMT の値 (= 仮想メソッドの先頭アドレス) から負のオフセットに置かれる次のフィールドを読む。
  VMT-0xc8: 自己ポインタ (値は VMT 自身)       VMT-0xa8: TypeInfo (kind 1 バイト + 名前の短い文字列)
  VMT-0x88: クラス名 (短い文字列へのポインタ)  VMT-0x80: インスタンスサイズ (8 バイト)
  VMT-0x78: 親 (値は親の VMT の格納位置)
各フィールドの値を表示し、自己ポインタ・TypeInfo 名・クラス名が一致するかを OK/NG で出す。
オフセットは 64-bit Delphi の VMT 配置を仮定する。仮定の検証は「3 者の名前が一致するか」で行う。
出力の VA は ImageBase を足した値 (py71_callers.py と同じ)。
"""
import sys

import pefile

path = sys.argv[1]
vmts = [int(v, 0) for v in sys.argv[2].split(",")]
slot = int(sys.argv[3], 0) if len(sys.argv) > 3 else None

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


def shortstr(va):
    off = va_to_off(va)
    if off is None:
        return None
    n = data[off]
    return data[off + 1:off + 1 + n].decode("latin-1")


def class_name(vmt):
    ti = u64(vmt - 0xA8)
    if ti is None or va_to_off(ti) is None:
        return None
    return shortstr(ti + 1)


for vmt in vmts:
    selfp = u64(vmt - 0xC8)
    ti = u64(vmt - 0xA8)
    cn = u64(vmt - 0x88)
    size = u64(vmt - 0x80)
    parent = u64(vmt - 0x78)
    ti_kind = None
    ti_name = None
    if ti is not None and va_to_off(ti) is not None:
        ti_kind = data[va_to_off(ti)]
        ti_name = shortstr(ti + 1)
    cn_name = shortstr(cn) if cn else None
    ok_self = "OK" if selfp == vmt else "NG"
    ok_name = "OK" if ti_name is not None and ti_name == cn_name else "NG"
    print(f"VMT {vmt:#x}")
    print(f"  [-0xc8] self      = {selfp:#x}  ({ok_self}: 自己を指す)")
    print(f"  [-0xa8] typeinfo  = {ti:#x}  kind={ti_kind} name={ti_name!r}")
    print(f"  [-0x88] classname = {cn:#x}  name={cn_name!r}  ({ok_name}: typeinfo 名と一致)")
    print(f"  [-0x80] instsize  = {size:#x}")
    pvmt = u64(parent) if parent and va_to_off(parent) is not None else None
    print(f"  [-0x78] parent    = {parent:#x}  -> parent VMT {pvmt:#x} ({class_name(pvmt)!r})" if pvmt else
          f"  [-0x78] parent    = {parent:#x}  -> (読めず)")
    if slot is not None:
        print(f"  [+{slot:#x}] slot    = {u64(vmt + slot):#x}")
