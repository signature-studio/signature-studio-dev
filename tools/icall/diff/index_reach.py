#!/usr/bin/env python3
# index_reach.py — ICALL-84 (#2900): 4 命令の添字参照が届き得る添字を求める (5 件の slot に対して)。
#   用法: python3 tools/icall/diff/index_reach.py [--base 0x...] <objdump -d -M intel の出力 (SlateCore.core_64)>
#   式: 添字 n = (slot - base - disp) / scale。slot ごとに整除できれば n を 1 つ得る (届く添字は列挙)。
#   基底 (既定 0x180000000):
#     - 180703913・180703b7c (r8・rbx): 各命令の直前で `lea r8|rbx,[rip+...]  # 0x180000000` (REPORT_APPENDIX_2900.md §2.1)。
#     - 1806dbe61・1806f7431 (rax): 基底 rax の設定番地は未確認 (REPORT_APPENDIX_2900.md §2.2)。0x180000000 は前提。
#   --base は負の対照用 (REPORT_APPENDIX_2900.md §3.2)。
#   出力: 命令ごとに、届く添字の列挙・最小・最大・整除できた件数。
import re
import sys

BASE = 0x180000000
SLOTS = [0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910]
# (命令 VA, 形の表示, disp, scale)
SITES = [
    (0x180703913, "[r8+rcx*8+0x125c7b8]", 0x125C7B8, 8),
    (0x180703B7C, "[rbx+rcx*8+0x125c7e8]", 0x125C7E8, 8),
    (0x1806DBE61, "[rbx+rax*1+0x125c440]", 0x125C440, 1),
    (0x1806F7431, "[rbx+rax*1+0x125c600]", 0x125C600, 1),
]


def reach(disp, scale, base):
    ns = []
    for s in SLOTS:
        d = s - base - disp
        if d % scale == 0:
            ns.append(d // scale)
    return ns


def main():
    args = sys.argv[1:]
    base = BASE
    if len(args) == 3 and args[0] == "--base":
        base = int(args[1], 16)
        args = args[2:]
    if len(args) != 1:
        print(__doc__)
        return 2
    lines = {}
    pat = re.compile(r"^\s*([0-9a-f]+):\t")
    with open(args[0], encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pat.match(line)
            if m:
                lines[int(m.group(1), 16)] = line.rstrip("\n")
    print(f"base = {base:#x}")
    for va, shape, disp, scale in SITES:
        text = lines.get(va, "(not found)")
        ns = reach(disp, scale, base)
        print(f"{va:#x} {shape} scale={scale} {'' if ns else 'no exact hit'}")
        print(f"    objdump: {text.split(chr(9), 2)[-1].strip() if text != '(not found)' else text}")
        if ns:
            print(f"    届く添字 (5 件のうち整除できた {len(ns)} 件): {', '.join(f'{n:,}' for n in ns)}")
            print(f"    min {min(ns):,} max {max(ns):,}")


if __name__ == "__main__":
    sys.exit(main())
