#!/usr/bin/env python3
"""PY-355 (#4696): 0x104caae の r9d 引数の G11 群 (入口 0x104aa21 など 4 辺) の到達 store 55 件を、式の型で分類する (実機不要)。

  python3 analysis/py355_g11.py <work/py53/fn.txt> <work/py53/g11.txt>

- 到達集合は py160_reach.py の `edges 0x104caae` 出力の 0x104aa21 行から取る (4 辺の集合は同一であることを確認する)。
- 直接 store は py88_writes.py の式の行 (`==>` の右) を型で分ける。
- 出力: 型ごとの件数と VA の一覧を g11.txt に書く (stdout に件数)。
"""
import os
import re
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE_ENTRIES = ["0x104aa21", "0x104aa2e", "0x104aa59", "0x104aa82"]


def reach_set(fn):
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "py160_reach.py"), fn, "edges", "0x104caae"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = {}
    for line in out.splitlines():
        m = re.match(r"(0x[0-9a-f]+) \S+ n=(\d+) \{(.*)\}", line.strip())
        if m:
            rows[m.group(1)] = [x.strip() for x in m.group(3).split(",")]
    sets = [rows[e] for e in EDGE_ENTRIES]
    if any(s != sets[0] for s in sets):
        sys.exit("G11 の 4 辺の到達集合が一致しない")
    return sets[0]


def classify(fn, items):
    direct = [x for x in items if x.startswith("0x")]
    ind = [x for x in items if x.startswith("IND")]
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "py88_writes.py"), fn] + direct,
        capture_output=True, text=True, check=True,
    ).stdout
    kinds = defaultdict(list)
    for line in out.splitlines():
        if not line.startswith("0x") or "==>" not in line:
            continue
        va, expr = line.split(":", 1)[0], line.split("==>", 1)[1].strip()
        if va == "0x1046d6b":
            k = "入口 (edx)"
        elif expr.startswith("VCALL"):
            k = "VCALL"
        elif expr.startswith("CALL"):
            k = "CALL"
        elif expr.startswith("rint("):
            k = "rint 型"
        elif expr.startswith("(M32") or expr.startswith("(M"):
            k = "rint 型 (F)"
        else:
            k = "直接式 (M32/M8/SLOT)"
        kinds[k].append(va)
    kinds["間接書込み (0xc61250 経由)"] = ind
    return kinds


def main():
    fn, dst = sys.argv[1], sys.argv[2]
    items = reach_set(fn)
    kinds = classify(fn, items)
    total = sum(len(v) for v in kinds.values())
    with open(dst, "w") as f:
        for k, v in kinds.items():
            f.write(f"{k}\t{len(v)}\t{' '.join(v)}\n")
    for k, v in kinds.items():
        print(f"{k}\t{len(v)}")
    print(f"total\t{total}")
    if total != 55:
        sys.exit(f"件数が 55 でない: {total}")


if __name__ == "__main__":
    main()
