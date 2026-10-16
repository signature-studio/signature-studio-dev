"""SHX-T56 (#5640): 画像全体の rip 相対参照先を基底とし、0x<TARGET> を指す表エントリ候補を列挙する。

使い方: scan_table_refs.py <m11_image.bin> <objdump -D -b binary -M intel の出力>
限界: 偶然一致を含む。候補は基底の用途 (表か定数か) を別途確認する。
"""
import re
import struct
import sys
from pathlib import Path

BASE = 0x400000
TARGET_VA = 0x6906D7  # 対象 VA (SHX-T56)
TARGET = TARGET_VA - BASE  # objdump 表示値・画像 offset と同じ空間 (LB_BASE=0 で offset = RVA)
NENT = 512
LEA_RIP = re.compile(r"lea\s+\w+,\[rip\+0x[0-9a-f]+\]\s+#\s+0x([0-9a-f]+)")
MOV_RIP = re.compile(r"\[rip\+0x[0-9a-f]+\]\s+#\s+0x([0-9a-f]+)")

img = Path(sys.argv[1]).read_bytes()
bases = set()
for line in Path(sys.argv[2]).read_text().splitlines():
    m = LEA_RIP.search(line) or MOV_RIP.search(line)
    if m:
        bases.add(int(m.group(1), 16))

hits = []
checked = 0
for tb in sorted(bases):
    off = tb
    if off < 0 or off >= len(img):
        continue
    checked += 1
    for ew, fmt in ((4, "<i"), (2, "<h"), (1, "<b")):
        for sc in (1, 2, 4, 8):
            for n in range(NENT):
                p = off + n * sc
                if p + ew > len(img):
                    break
                rel = struct.unpack_from(fmt, img, p)[0]
                if tb + rel == TARGET:
                    hits.append((tb, ew, sc, n))
print(f"基底 (rip 相対 lea/mov の target, distinct): {len(bases)} / 画像内で検査: {checked}")
print(f"0x{TARGET_VA:x} (offset 0x{TARGET:x}) を指す (基底 + 相対値) の候補: {len(hits)} 件")
for h in hits[:40]:
    print(f"base={h[0]:#x} w={h[1]} scale={h[2]} idx={h[3]}")
