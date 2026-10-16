#!/usr/bin/env python3
"""PLG-P0b-67 (#5871): PE 全体のバイト列検索で関数表 TABLE_VA の格納を探す。

hs_tbl_refs.py (rip 相対) と hs_tbl_abs.py (絶対 disp・即値) の補完。
PE ファイル全体 (block00031_PE.bin) を、TABLE_VA を little-endian で並べたバイト列として検索する:
  - 8 バイト: TABLE_VA (qword) の格納 (関数表ポインタ・構造体フィールド)
  - 4 バイト: TABLE_VA (dword) の格納 (disp32 / 即値)

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> python3 hs_tbl_bytes.py [TABLE_VA WIDTH]
引数なしは 0x12B0380 (8 バイト) と 0x12B02E0 (4 バイト) を両方調べる。WIDTH は 8 または 4。
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')


def find_all(data, pat):
    hits = []
    pos = data.find(pat)
    while pos != -1:
        hits.append(pos)
        pos = data.find(pat, pos + 1)
    return hits


def main():
    with open(PE_PATH, 'rb') as f:
        data = f.read()
    print('PE: %s (%d bytes)' % (PE_PATH, len(data)))
    if len(sys.argv) == 3:
        jobs = [(int(sys.argv[1], 16), int(sys.argv[2]))]
    else:
        jobs = [(0x12B0380, 8), (0x12B02E0, 4)]
    for table, width in jobs:
        fmt = '<Q' if width == 8 else '<I'
        pat = struct.pack(fmt, table)
        hits = find_all(data, pat)
        print('%s (%d バイト): %d 件' % (hex(table), width, len(hits)))
        for h in hits[:20]:
            print('  file offset %s' % hex(h))


if __name__ == '__main__':
    main()
