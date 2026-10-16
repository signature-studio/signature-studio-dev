#!/usr/bin/env python3
# #5718 (PY-5384): objdump の VA (ImageBase 込み) が DLL 内のデータ (関数ポインタ表・vtable 等) に現れるかを走査する。
# 使い方: python3 tools/flp/s9_fnptr_scan.py <block00031_PE.bin> <VA hex>...
# objdump のラベルは絶対 VA (ImageBase 0x400000 込み) なので、ここでは base を足さない。
# 8 バイト・4 バイトの little-endian を全ファイルから探す。表示する位置はファイル offset。
import struct
import sys


def find_all(data, pat):
    hits = []
    i = data.find(pat)
    while i != -1:
        hits.append(i)
        i = data.find(pat, i + 1)
    return hits


def main(argv):
    with open(argv[1], 'rb') as f:
        data = f.read()
    for t in argv[2:]:
        va = int(t, 16)
        h8 = find_all(data, struct.pack('<Q', va))
        h4 = find_all(data, struct.pack('<I', va))
        print(f'VA {va:#x}: 8byte {len(h8)} 件 {[hex(h) for h in h8[:10]]} / 4byte {len(h4)} 件 {[hex(h) for h in h4[:10]]}')


if __name__ == '__main__':
    main(sys.argv)
