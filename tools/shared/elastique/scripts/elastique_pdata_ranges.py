#!/usr/bin/env python3
"""élastique_x64.dll の .pdata のうち .text 内の関数範囲を "<begin> <end>" (16 進 VA・排他) の 1 行 1 関数で出す (T-SH-110 / #4284)。

elastique_facts.py の pdata_funcs・parse_pe をそのまま使う (件数の出典は REPORT_4284.md §0)。
使い方: python3 elastique_pdata_ranges.py <dll> > ranges.txt
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elastique_facts import parse_pe, pdata_funcs  # noqa: E402


def main():
    raw = open(sys.argv[1], "rb").read()
    base, sections, image, dd = parse_pe(raw)
    txt = {s["name"]: s for s in sections}[".text"]
    lo, hi = base + txt["va"], base + txt["va"] + txt["vsize"]
    for b, e in pdata_funcs(image, base, dd):
        if lo <= b < hi:
            print(f"0x{b:x} 0x{e:x}")


if __name__ == "__main__":
    main()
