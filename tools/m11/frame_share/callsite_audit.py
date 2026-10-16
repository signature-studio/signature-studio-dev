#!/usr/bin/env python3
"""SHX-T50 (#5587): function_6905f0 -> function_690580 の機械語 call site と、
直前ブロックの到達性 (直接分岐・絶対参照による入口の有無) を判定する。

入力: work/m11_image.bin (VA - 0x400000 = file offset)。
出力: 標準出力に site ごとの表 (Markdown)。
限界: switch テーブル (相対オフセット方式) の飛び先は走査しない。
"""
import struct
import sys
from pathlib import Path

IMG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/m11/work/m11_image.bin")
BASE = 0x400000
# IR に call が残る 2 site (0x69073b・0x6909d4) は到達性の判定対象外 (IR の grep で確認する)。
SITES = [0x6906EC, 0x690804, 0x6908B3]
# 欠落 site の直前ブロック先頭 (DSM の境界。nop パディング直後)。
BLOCKS = {0x6906EC: 0x6906D7, 0x690804: 0x6907F7, 0x6908B3: 0x6908A4}


def scan_targets(img: bytes, targets: set[int]) -> dict[int, list[str]]:
    hits: dict[int, list[str]] = {t: [] for t in targets}
    n = len(img)
    # rel8 jcc/jmp (70-7f, eb) と rel32 jcc/jmp/call/lea 相当 (0f 8x, e8, e9)
    for i in range(n - 6):
        op = img[i]
        if 0x70 <= op <= 0x7F or op == 0xEB:
            rel = struct.unpack_from("<b", img, i + 1)[0]
            tgt = BASE + i + 2 + rel
            if tgt in targets:
                hits[tgt].append(f"rel8@{BASE + i:#x}")
        if op in (0xE8, 0xE9):
            rel = struct.unpack_from("<i", img, i + 1)[0]
            tgt = BASE + i + 5 + rel
            if tgt in targets:
                hits[tgt].append(f"rel32@{BASE + i:#x}")
        if op == 0x0F and i + 6 <= n and 0x80 <= img[i + 1] <= 0x8F:
            rel = struct.unpack_from("<i", img, i + 2)[0]
            tgt = BASE + i + 6 + rel
            if tgt in targets:
                hits[tgt].append(f"jcc32@{BASE + i:#x}")
    return hits


def scan_absolute(img: bytes, targets: set[int]) -> dict[int, list[str]]:
    hits: dict[int, list[str]] = {t: [] for t in targets}
    for t in targets:
        for width, fmt in ((4, "<I"), (8, "<Q")):
            pat = struct.pack(fmt, t)
            start = 0
            while True:
                j = img.find(pat, start)
                if j < 0:
                    break
                hits[t].append(f"abs{width * 8}@{BASE + j:#x}")
                start = j + 1
    return hits


def main() -> int:
    img = IMG.read_bytes()
    starts = set(BLOCKS.values())
    rel = scan_targets(img, starts)
    ab = scan_absolute(img, starts)
    print("| site | 直前ブロック | 直接分岐 | 絶対参照 | 判定 |")
    print("|---|---|---|---|---|")
    for s in SITES:
        b = BLOCKS.get(s)
        if b is None:
            print(f"| {s:#x} | (無し) | - | - | 到達 (前ブロック無し) |")
            continue
        r = rel[b]
        a = ab[b]
        verdict = "入口あり" if (r or a) else "入口なし (直接参照なし)"
        print(f"| {s:#x} | {b:#x} | {len(r)} | {len(a)} | {verdict} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
