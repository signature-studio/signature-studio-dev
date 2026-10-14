#!/usr/bin/env python3
"""PY-67 (#2159): 指定 VA の 8 バイト値を読む (実機不要)。

  python3 analysis/py67_qword.py <PE.bin> <VA hex>[,<VA hex>...]          # 各 VA の 8 バイト値
  python3 analysis/py67_qword.py <PE.bin> <VA hex>[,<VA hex>...] find     # その VA の値を 8 バイトで持つ箇所 (絶対参照)

VA は ImageBase を含む絶対アドレス (py58_context.py と同じ)。.text に置かれた
VMT 自身や、.data・.bss の class ref スロットの中身を確かめるのに使う。
.bss など SizeOfRawData の外 (ファイルに実体が無い) の VA は値を出さない。
find は、ファイル全体で同じ 8 バイトの並びを探す (VA を値として持つ箇所)。
"""
import struct
import sys

import pefile

path = sys.argv[1]
vas = [int(v, 0) for v in sys.argv[2].split(",")]
find = len(sys.argv) > 3 and sys.argv[3] == "find"

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = open(path, "rb").read()

for va in vas:
    if find:
        pat = struct.pack("<Q", va)
        hits = []
        i = data.find(pat)
        while i != -1:
            hits.append(i)
            i = data.find(pat, i + 1)
        print(f"{va:#x} abs8 hits (file offset): {[hex(h) for h in hits]}")
        continue
    rva = va - base
    sec = next(s for s in pe.sections if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData))
    name = sec.Name.rstrip(bytes(1)).decode()
    inner = rva - sec.VirtualAddress
    if inner + 8 > sec.SizeOfRawData:
        print(f"{va:#x} in {name}: ファイルに実体なし (SizeOfRawData 外。値は出さない)")
        continue
    off = sec.PointerToRawData + inner
    value = struct.unpack_from("<Q", data, off)[0]
    print(f"{va:#x} in {name} qword = {value:#x}")
