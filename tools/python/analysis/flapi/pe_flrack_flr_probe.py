#!/usr/bin/env python3
"""FLEngine PE に `flrack.flr` という属性名があるかを確定する (PY-167 #3181 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_flr_probe.py

全 block*_PE.bin を走査し、(1) NUL 終端の `flr` (属性名・型名として載る形) の件数と位置と、
部分一致 (`flr` を含む英数_. の連続) の全 block 合計、(2) `flrack` で始まる NUL 終端の名前 (モジュール名・型名) の VA、
(3) block00031_PE.bin の部分一致の一覧 (VA 付き) を出す。
属性名は CPython の PyMethodDef / PyMemberDef / PyModule_AddObject のいずれでも NUL 終端の C 文字列で載るため、
`flr\\0` が 0 件なら C 側に `flr` という名前の属性は無い。
"""
import glob
import os
import re

import pefile

FLR = re.compile(rb"(?<![A-Za-z0-9_.])flr\x00")
FLRACK = re.compile(rb"(?<![A-Za-z0-9_.])flrack(?:\.[A-Za-z_]+)?\x00")
PART = re.compile(rb"[A-Za-z0-9_.]*flr[A-Za-z0-9_.]*")


def main():
    base = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
    print("# (1) NUL 終端の flr (block ごと)")
    total = 0
    part_total = 0
    for path in sorted(glob.glob(os.path.join(base, "block*_PE.bin"))):
        raw = open(path, "rb").read()
        if raw[:2] != b"MZ":
            continue
        n = len(FLR.findall(raw))
        total += n
        part_total += len(PART.findall(raw))
        if n:
            print(f"  {os.path.basename(path)}: {n} 件")
    print(f"  合計 {total} 件")
    print(f"  部分一致 (flr を含む英数_. の連続) 全 block 合計 {part_total} 件")

    raw = open(os.path.join(base, "block00031_PE.bin"), "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def off2va(off):
        for v, _, praw, rs in secs:
            if praw <= off < praw + rs:
                return image_base + v + (off - praw)
        return None

    print("# (2) flrack で始まる NUL 終端の名前 (block00031_PE.bin)")
    for m in FLRACK.finditer(raw):
        va = off2va(m.start())
        name = m.group(0)[:-1].decode("latin1")
        print(f"  {va:#x} {name}" if va is not None else f"  (no VA) {name}")
    print("# (3) 部分一致 (flr を含む英数_. の連続) (block00031_PE.bin)")
    for m in PART.finditer(raw):
        va = off2va(m.start())
        name = m.group(0).decode("latin1")
        print(f"  {va:#x} {name}" if va is not None else f"  (no VA) {name}")


if __name__ == "__main__":
    main()
