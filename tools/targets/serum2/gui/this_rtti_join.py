#!/usr/bin/env python3
"""SR-82 #4930 受入 2: THIS / THIS-CHILD の所属関数 F について、F の入口を含む vtable 形の表の RTTI クラス名を集計する (静的)。

入力: receiver_this_trace.py の --tsv 出力 (trace.tsv) と arg_vtable_callers.py --cats vptr:THIS,vptr:THIS-CHILD --tsv の出力 (rtti.tsv)。
出力: 分類ごとの関数数・RTTI の有無・SerumController の RTTI を持つ関数。
限界: RTTI は「F が仮想関数として登録された表の所属 class」であり、F の this が指す object の型ではない。
RTTI が無い関数 (表に現れない・RTTI が '?') は判定できない。
usage: this_rtti_join.py <trace.tsv> <rtti.tsv>
"""
import sys
from collections import defaultdict

TRACE, RTTI = sys.argv[1], sys.argv[2]
CATS = ("vptr:THIS", "vptr:THIS-CHILD")
SC = "SerumController"

rtti = defaultdict(set)
with open(RTTI) as f:
    next(f)
    for line in f:
        func, _n, _head, _k, name = line.rstrip("\n").split("\t")
        rtti[int(func, 16)].add(name)

funcs = defaultdict(set)
with open(TRACE) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in CATS:
            funcs[cols[4]].add(int(cols[1], 16))

for cat in CATS:
    fs = funcs[cat]
    named = {f for f in fs if any(x not in ("-", "?") for x in rtti.get(f, ()))}
    sc = {f for f in fs if any(SC in x for x in rtti.get(f, ()))}
    print(f"{cat}: 関数 {len(fs)} / RTTI あり {len(named)} / RTTI なし {len(fs) - len(named)} / SerumController の RTTI を持つ関数 {len(sc)}")
    for f in sorted(sc):
        print(f"  {f:#x} {sorted(x for x in rtti[f] if SC in x)}")
