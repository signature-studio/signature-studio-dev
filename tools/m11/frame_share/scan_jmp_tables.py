"""SHX-T56 (#5640) 方法 A: 間接 jmp reg の直前 WINDOW 命令から、添字読み出し (index*scale) と rip 相対 lea の基底を対応づけ、
基底 + 相対値が TARGET を指す表エントリを探す。

使い方: scan_jmp_tables.py <m11_image.bin> <objdump -D -b binary -m i386:x86-64 -M intel の出力>
限界: 窓 (直前 WINDOW 命令) に依存する。窓外の飛び先・表でない計算による飛び先は対象外。
"""
import re
import struct
import sys
from pathlib import Path

BASE = 0x400000
TARGET = 0x6906D7  # 対象 VA (SHX-T56)
WINDOW = 40
NENT = 512
WIDTH = {"BYTE": 1, "WORD": 2, "DWORD": 4, "QWORD": 8}
JMP_REG = re.compile(r"^jmp\s+(r(?:[a-d]x|[sd]i|[bs]p|\d+))$")
LEA_RIP = re.compile(r"^lea\s+\w+,\[rip\+0x[0-9a-f]+\]\s+#\s+0x([0-9a-f]+)")
LOAD = re.compile(r"^(movsxd|movsx|movzx|mov)\s+\w+,\s*(?:(BYTE|WORD|DWORD|QWORD) PTR )?\[([^\]]+)\]")
SCALE = re.compile(r"\*(\d)")

img = Path(sys.argv[1]).read_bytes()
insns = []
for line in Path(sys.argv[2]).read_text().splitlines():
    parts = line.split("\t")
    if len(parts) >= 3 and parts[0].strip().endswith(":") and parts[2].strip():
        insns.append(parts[2].strip())

jumps = [i for i, t in enumerate(insns) if JMP_REG.match(t)]
hits = []
windows_with_base_and_load = 0
for i in jumps:
    win = insns[max(0, i - WINDOW):i]
    bases = set()
    loads = set()
    for t in win:
        m = LEA_RIP.match(t)
        if m:
            bases.add(int(m.group(1), 16))
        m = LOAD.match(t)
        if m and m.group(2) and "*" in m.group(3):
            sc = int(SCALE.search(m.group(3)).group(1))
            loads.add((WIDTH[m.group(2)], sc))
    if not (bases and loads):
        continue
    windows_with_base_and_load += 1
    for tb in sorted(bases):
        off = tb - BASE
        if off < 0 or off >= len(img):
            continue
        for ew, sc in sorted(loads):
            fmt = {1: "<b", 2: "<h", 4: "<i", 8: "<q"}[ew]
            for n in range(NENT):
                p = off + n * sc
                if p + ew > len(img):
                    break
                rel = struct.unpack_from(fmt, img, p)[0]
                if tb + rel == TARGET:
                    hits.append((i, tb, ew, sc, n))

print(f"間接 jmp reg: {len(jumps)} 件 / 添字読み出しと rip 基底を両方含む窓: {windows_with_base_and_load} 件")
print(f"0x{TARGET:x} を指す表エントリ: {len(hits)} 件")
for h in hits[:40]:
    print(f"jmp#{h[0]} base={h[1]:#x} w={h[2]} scale={h[3]} idx={h[4]}")
