#!/usr/bin/env python3
"""flapi_table.json の stub 署名 (sig.params の個数) と PE 書式 (kwsig.max) の引数数の一致を数える (PY-70 / #2500)。

  git show <rev>:tools/python/analysis/flapi/flapi_table.json > before.json
  python3 analysis/flapi/sig_arity_check.py before.json analysis/flapi/flapi_table.json

対象: sig と kwsig.max の両方を持つ関数。一致 = sig.params の個数が kwsig.max に等しい。
"""
import json
import sys


def arities(path):
    out = {}
    for m, fs in json.load(open(path))["modules"].items():
        for n, e in fs.items():
            kw, sig = e.get("kwsig") or {}, e.get("sig")
            if kw.get("max") is not None and sig:
                out[f"{m}.{n}"] = (len(sig["params"]), kw["max"])
    return out


before, after = arities(sys.argv[1]), arities(sys.argv[2])
for label, d in (("before", before), ("after", after)):
    agree = sorted(k for k, (p, mx) in d.items() if p == mx)
    print(f"{label}: 対象 {len(d)} 件・一致 {len(agree)}・不一致 {len(d) - len(agree)}")
changed = sorted(k for k in after if before.get(k, (None, None))[0] != after[k][0])
print(f"署名の引数個数が変わった関数: {len(changed)} 件")
for k in changed:
    print(f"  {k}: {before.get(k, (None, None))[0]} -> {after[k][0]} (PE max {after[k][1]})")
print("不一致 (after):", " ".join(sorted(f"{k}:{p}/{mx}" for k, (p, mx) in after.items() if p != mx)))
