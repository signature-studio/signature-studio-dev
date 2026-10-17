#!/usr/bin/env python3
"""PY-5390 (#5801): 判定 (mask 0x4 tail 側) ごとに、名指しの呼出し先の直接 call 閉包が、グローバル `0x16bd1d8`・`0x16bd1e0`・`0x16bd1a8` の書込み関数・読み関数に届くかを数える (実機不要)。

  python3 analysis/py5801_reach.py <PE.bin> <work/py4769/r8d_single.tsv> <outdir> [--appendix=<path>]

入力: py4769 の TSV (mask 0x4 かつ tail 到達側)。py5801_callees2 と同じ 1 段目 (NAMED) を起点にする。
閉包: 直接 call (`call 0x...`) だけを辿る。間接 call・間接 jmp は閉包に含めない (件数は別に出す)。深さは DEPTH。
注意: 届く = 必要条件の確認であって、届いた読みが判定の分岐条件に入ったことの証明ではない。
"""
import csv
import os
import sys

import capstone

from py381_r8d_callees import load_pe, walk
from py5801_callees2 import NAMED, direct_calls

DEPTH = 4
WRITERS = {0x11F16B0: "0x16bd1d8/0x16bd1e0 書", 0x11F1A20: "0x16bd1a8 書"}
READERS = {0x11FC770: "0x16bd1d8/0x16bd1e0 読", 0x1192F80: "0x16bd1a8 読"}
TARGETS = {**WRITERS, **READERS}


def closure(md, start, raw, roots, cache):
    """roots から直接 call を DEPTH 段まで辿る。返り値: {関数: 最短深さ}。"""
    depth = {r: 1 for r in roots}
    frontier = list(roots)
    for d in range(2, DEPTH + 1):
        nxt = []
        for f in frontier:
            if f not in cache:
                cache[f] = walk(md, start, raw, f)
            for c in direct_calls(cache[f][0]):
                if c not in depth:
                    depth[c] = d
                    nxt.append(c)
        frontier = nxt
    return depth


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    appendix = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--appendix=")), None)
    pe_path, tsv_path, outdir = args[0], args[1], args[2]
    start, raw = load_pe(pe_path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    sides = []
    with open(tsv_path) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["mask"] != "0x4" or r["tail"] != "True":
                continue
            cs = []
            for c in r["calls"].split(";"):
                if ":" not in c or c == "-":
                    continue
                t = c.split(":", 1)[1]
                if t.startswith("0x"):
                    cs.append(int(t, 16))
            sides.append((r["site"], r["side"], cs))

    cache = {}
    rows = []
    for site, side, cs in sides:
        named = [t for t in NAMED if t in cs]
        if not named:
            continue
        cl = closure(md, start, raw, named, cache)
        hit = sorted((t, cl[t]) for t in TARGETS if t in cl)
        rows.append((site, side, named, hit, len(cl)))

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "reach.tsv"), "w") as f:
        f.write("site\tside\tnamed\tclosure_size\thits\n")
        for site, side, named, hit, n in rows:
            hs = " ".join(f"{t:#x}@{d}" for t, d in hit) or "-"
            f.write(f"{site}\t{side}\t{' '.join(f'{x:#x}' for x in named)}\t{n}\t{hs}\n")

    if appendix:
        lines = ["# PY-5390 (#5801) 付録: 判定ごとの直接 call 閉包が届くグローバル書込み・読み関数", "",
                 f"> 生成元: `analysis/py5801_reach.py <PE.bin> <work/py4769/r8d_single.tsv> <outdir> --appendix=<path>` の出力 (解析器が書く)。深さ DEPTH={DEPTH}・直接 call のみ。",
                 "> 届く = 必要条件。届いた読みが判定の分岐条件に入ったことは示さない。", "",
                 "| 判定 | 側 | 名指しの 1 段目 | 閉包の関数数 | 届く関数 (深さ) |", "|---|---|---|---|---|"]
        for site, side, named, hit, n in rows:
            hs = " ".join(f"{t:#x}({TARGETS[t]}, d={d})" for t, d in hit) or "-"
            lines.append(f"| {site} | {side} | {' '.join(f'{x:#x}' for x in named)} | {n} | {hs} |")
        with open(appendix, "w") as f:
            f.write("\n".join(lines) + "\n")

    print(f"sides={len(sides)} with_named={len(rows)} reach_any={sum(1 for r in rows if r[3])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
