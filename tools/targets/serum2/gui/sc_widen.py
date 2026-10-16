#!/usr/bin/env python3
"""SR-82 #4930 受入 2: THIS / THIS-CHILD の所属関数 F の SC 証拠を、SC 伝播を広げて数える (静的)。

入力: Serum2_win64.vst3 (PE)。trace.tsv (receiver_this_trace.py --tsv 出力、cat_strict 列を読む)。
方法: receiver_this_trace の SC 閉包 (strict: 支配関係を満たす rcx の this のみ) を起点 (tier S/K/C) とし、
  そこから直接 call の宛先 f へ伸ばす。strict で rcx が this なら tier C、strict では外れるが loose (支配を見ない) で
  rcx が this なら tier L (参考・分岐の反対側の定義を拾い得る)。不動点まで伸ばす。
証拠の定義: 行の所属関数 F が tier S/K/C なら strict 証拠、tier L なら loose 証拠、どちらでもなければ証拠無し。
限界: 間接 call の宛先は伸ばさない。THIS-CHILD は、呼出元 F の this が SC であることを証拠とする
  (子オブジェクトの生成元までは遡らない)。
usage: sc_widen.py <pe> <trace.tsv> [--tsv out.tsv]
"""
import contextlib
import io
import re
import sys
from collections import Counter

ARGS = sys.argv
pe_path, tsv_in = ARGS[1], ARGS[2]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None

sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R

tier = {f: "S/K/C" for f in R.SC}
frontier = list(R.SC)
grow = Counter()
while frontier:
    g = frontier.pop()
    if g not in R.by_func:
        continue
    fn = R.get_fn(g)
    for i, ins in enumerate(fn.ins):
        if ins.mnemonic != "call" or not re.fullmatch(r"0x[0-9a-f]+", ins.op_str):
            continue
        f = int(ins.op_str, 16)
        if f in tier or R.func_of(f) != f:
            continue
        if R.origin(fn, i, "rcx", True) == ("this", []):
            tier[f] = "C"
            grow["strict"] += 1
            frontier.append(f)
        elif R.origin(fn, i, "rcx", False) == ("this", []):
            tier[f] = "L"
            grow["loose-only"] += 1
            frontier.append(f)

print(f"SC 閉包: strict {len(R.SC)} 関数 / 伝播で追加 {dict(grow)} / 合計 {len(tier)} 関数")

rows = []
with open(tsv_in) as fh:
    next(fh)
    for line in fh:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in ("vptr:THIS", "vptr:THIS-CHILD"):
            f = int(cols[1], 16)
            rows.append((cols[4], f, tier.get(f, "-")))

for cat in ("vptr:THIS", "vptr:THIS-CHILD"):
    sub = [r for r in rows if r[0] == cat]
    ev = Counter(r[2] for r in sub)
    nf = len({r[1] for r in sub})
    print(f"{cat} = {len(sub)} 件 / 所属関数 {nf} 個 / 証拠別 {dict(ev)}")

if TSV:
    with open(TSV, "w") as fh:
        fh.write("cat\tfunc\ttier\n")
        for cat, f, t in rows:
            fh.write(f"{cat}\t{f:#x}\t{t}\n")
