#!/usr/bin/env python3
"""PY-63 (#2030): 指定 VA を指す参照を PE 内で探す (実機不要)。

  python3 analysis/py63_refs.py <PE.bin> <VA hex,VA hex,...>

- rel32 の直接 call/jmp: 変換先が VA になる命令を .text 全体から列挙する。
- abs64 の関数ポインタ: 8 バイト little-endian の絶対アドレスを PE 全体から検索する
  (vtable・関数ポインタ表の検出用。間接呼出しの呼出し元候補)。
"""
import struct
import sys

import pefile

path = sys.argv[1]
vas = [int(v, 0) for v in sys.argv[2].split(",")]

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff = text.PointerToRawData
tsize = text.SizeOfRawData
tbase = base + text.VirtualAddress
tdata = data[toff:toff + tsize]

for va in vas:
    print(f"===== refs to {va:#x} =====")

    rel = []
    for i in range(len(tdata) - 4):
        if tdata[i] not in (0xE8, 0xE9):
            continue
        disp = struct.unpack_from("<i", tdata, i + 1)[0]
        ins_va = tbase + i
        if ins_va + 5 + disp == va:
            rel.append(ins_va)
    print(f"  rel32 call/jmp: {[hex(x) for x in rel] or 'none'}")

    ab = struct.pack("<Q", va)
    hits = []
    start = 0
    while True:
        j = data.find(ab, start)
        if j < 0:
            break
        hits.append(j)
        start = j + 1
    print(f"  abs64 occurrences in file: {[hex(h) for h in hits[:20]] or 'none'}")
    for h in hits[:20]:
        sec = next((s for s in pe.sections if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData), None)
        name = sec.Name.rstrip(b"\0").decode(errors="replace") if sec else "?"
        print(f"    file_off={h:#x} section={name}")
    print()
