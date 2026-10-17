#!/usr/bin/env python3
"""SR-95 #5987: join.tsv の証拠なし行 (evidence=none) が SerumController 由来かを、既存 TSV だけから判定する (静的・PE 不要)。

判定 (行ごと・所属関数 F の証拠で分ける):
  F が SC 関数集合に入る                         -> SC 証拠 (self)
  直接呼出元 (direct.tsv) に SC の関数がある      -> SC 証拠 (direct)
  vtable 候補 (vt_ind.tsv の n_sites_sc > 0)     -> SC 証拠 (vtable)
  上記のどれも無く、呼出元が見つからない          -> 呼出元なし (SC 由来の証拠は無い・非 SC とは断定しない)
入力:
  join.tsv    : arg_row_join.py --tsv 出力 (cat / func / evidence)
  direct.tsv  : arg_caller_types.py --tsv 出力 (func / caller)
  vt_ind.tsv  : arg_vt_indirect.py --tsv 出力 (func / n_sites / n_sites_sc)
  sc.txt      : SC 関数集合 (1 行 1 アドレス・0x 付き)。receiver_this_trace.py の sc_closure() の結果
usage: arg_none_sc_judge.py <join.tsv> <direct.tsv> <vt_ind.tsv> <sc.txt>
"""
import csv
import sys
from collections import Counter


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


join_p, direct_p, vt_p, sc_p = sys.argv[1:5]
SC = {int(x, 16) for x in open(sc_p).read().split() if x.strip()}
direct_callers = {}
for r in read(direct_p):
    direct_callers.setdefault(int(r["func"], 16), set()).add(int(r["caller"], 16))
vt_sc = {}
vt_n = {}
for r in read(vt_p):
    f = int(r["func"], 16)
    vt_sc[f] = vt_sc.get(f, 0) + int(r["n_sites_sc"])
    vt_n[f] = vt_n.get(f, 0) + int(r["n_sites"])

rows = [r for r in read(join_p) if r["evidence"] == "none"]
out = Counter()
for r in rows:
    f = int(r["func"], 16)
    if f in SC:
        k = "SC 証拠 (self)"
    elif direct_callers.get(f, set()) & SC:
        k = "SC 証拠 (direct)"
    elif vt_sc.get(f, 0) > 0:
        k = "SC 証拠 (vtable)"
    elif vt_n.get(f, 0) > 0:
        k = "呼出元なし (vtable 候補は非 SC のみ)"
    else:
        k = "呼出元なし (候補 0)"
    out[(r["cat"], k)] += 1

for cat in ("vptr:ARG", "vptr:ARG-CHILD"):
    total = sum(v for (c, _), v in out.items() if c == cat)
    print(f"{cat} 証拠なし {total} 件")
    for (c, k), v in sorted(out.items()):
        if c == cat:
            print(f"  {k}: {v}")
print(f"証拠なし計 {len(rows)} 件 / SC 証拠あり {sum(v for (_, k), v in out.items() if k.startswith('SC'))} 件")
