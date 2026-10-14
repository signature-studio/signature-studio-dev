#!/usr/bin/env python3
"""PY-159 (#3086): 65 件の [rbp+0x5b8] 書込みの式を、REPORT 用の Markdown 表として出す (実機不要)。

  python3 analysis/py159_table.py <work/py53/fn.txt> [<VA> ...]

- 式は py88_writes.Slicer の出力 (書く値の式)。未確定印は py88_writes.category と同じ規則。
- 読む値 (書込み前の ACC) は式中の ACC。合流を越える frame 変数は SLOT[rbp+X]? として残す。
- 手計算突合 列: py159_check_hand.py の 7 件 (一致) に ✓。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as w  # noqa: E402
import py159_check_hand as hc  # noqa: E402

CHECKED = {va for va, _ in hc.hand_entries(None)}


def main():
    path = sys.argv[1]
    ins, order = w.load(path)
    s = w.Slicer(ins, order)
    targets = [int(x, 16) for x in sys.argv[2:]] or w.default_targets(path)
    print("| # | 書込み VA | 命令 | 書く値の式 (機械スライス) | 未確定印 | 手計算突合 |")
    print("|---:|---|---|---|---|:---:|")
    for n, a in enumerate(targets, 1):
        m, o = ins[a]
        val = s.ev(w.parse_ops(o)[1], s.idx[a], 0)
        mark = "✓" if a in CHECKED else ""
        print(f"| {n} | `{a:#x}` | `{m} {o}` | `{val}` | {w.category(val)} | {mark} |")


if __name__ == "__main__":
    main()
