#!/usr/bin/env python3
"""SR-94 #5612: trace の ARG / ARG-CHILD 行ごとに、所属関数 F の証拠 (直接呼出元・vtable 候補) を突き合わせる (静的・PE 不要)。

入力は前段の TSV のみ:
  trace.tsv   : receiver_this_trace.py --tsv 出力 (cat_strict が vptr:ARG / vptr:ARG-CHILD の行)
  direct.tsv  : arg_caller_types.py --tsv 出力 (func 列 = 直接呼出元がある F)
  vt_args.tsv : arg_vt_args.py --tsv 出力 (func 列 = vtable 候補がある F)
出力: 証拠の組み合わせ (direct / vtable / both / none) ごとの行数。both は直接と vtable の両方を持つ行。
usage: arg_row_join.py <trace.tsv> <direct.tsv> <vt_args.tsv> [--tsv out.tsv]
"""
import csv
import sys
from collections import Counter

ARGS = sys.argv
trace_p, direct_p, vt_p = ARGS[1], ARGS[2], ARGS[3]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


trace = [r for r in read(trace_p) if r["cat_strict"] in ("vptr:ARG", "vptr:ARG-CHILD")]
dF = {r["func"] for r in read(direct_p)}
vF = {r["func"] for r in read(vt_p)}

rows = []
for r in trace:
    F = r["func"]
    ev_d = F in dF
    ev_v = F in vF
    if ev_d and ev_v:
        kind = "both"
    elif ev_d:
        kind = "direct"
    elif ev_v:
        kind = "vtable"
    else:
        kind = "none"
    rows.append((r["cat_strict"], F, kind))

cnt = Counter((cat, kind) for cat, _, kind in rows)
for cat in ("vptr:ARG", "vptr:ARG-CHILD"):
    total = sum(v for (c, _), v in cnt.items() if c == cat)
    parts = " / ".join(f"{k} {cnt[(cat, k)]}" for k in ("direct", "vtable", "both", "none"))
    print(f"{cat} 計 {total} 件: {parts}")
both = sum(1 for _, _, k in rows if k == "both")
print(f"直接と vtable の両方の証拠を持つ行 = {both} 件 (重なりの確認)")
print(f"証拠あり (direct / vtable / both のいずれか) = {sum(1 for _, _, k in rows if k != 'none')} 件")

if TSV:
    with open(TSV, "w") as fh:
        fh.write("cat\tfunc\tevidence\n")
        for cat, F, kind in rows:
            fh.write(f"{cat}\t{F}\t{kind}\n")
