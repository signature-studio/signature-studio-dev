#!/usr/bin/env python3
"""#2295 (PLG-F3-26): 対象 VA への jcc (0f 8x / 7x) と jmp (eb / e9) の出現位置を生バイト走査で出す。

callsite_scan.py は e8/e9 (call/jmp rel32) の直接呼出しだけを見るため、この script で jcc・jmp rel8 を補う。
生バイト走査なので偽陽性はあり得るが、0 件は偽陰性なし (命令境界に依らず全バイト位置を見る)。

使い方: python3 tools/plugins/f2/jump_scan.py <block_PE.bin> <target_hex> [<target_hex> ...]
"""
import struct
import sys

from callsite_scan import load


def main():
    base, img, _ = load(sys.argv[1])
    targets = [int(x, 16) for x in sys.argv[2:]]
    hits = {t: [] for t in targets}
    n = len(img)
    for i in range(n - 1):
        b = img[i]
        if b == 0x0F and i + 6 <= n and 0x80 <= img[i + 1] <= 0x8F:
            tgt = base + i + 6 + struct.unpack_from('<i', img, i + 2)[0]
            kind = 'jcc32'
        elif 0x70 <= b <= 0x7F and i + 2 <= n:
            tgt = base + i + 2 + struct.unpack_from('<b', img, i + 1)[0]
            kind = 'jcc8'
        elif b == 0xEB and i + 2 <= n:
            tgt = base + i + 2 + struct.unpack_from('<b', img, i + 1)[0]
            kind = 'jmp8'
        elif b == 0xE9 and i + 5 <= n:
            tgt = base + i + 5 + struct.unpack_from('<i', img, i + 1)[0]
            kind = 'jmp32'
        else:
            continue
        if tgt in hits:
            hits[tgt].append((kind, base + i))
    for t in targets:
        print(f'[jcc/jmp] {hex(t)}: {len(hits[t])} 件 ' + ' '.join(f'{k}@{hex(a)}' for k, a in hits[t][:20]))


if __name__ == '__main__':
    main()
