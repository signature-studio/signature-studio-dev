#!/usr/bin/env python3
"""sig_arity_check.py が不一致とする関数について、不一致の根拠を stub 宣言と PE 書式から並べる (PY-102 / #2883)。

  FL_STUBS_DIR=<FL-Studio-API-Stubs の clone> python3 analysis/flapi/sig_mismatch_evidence.py [flapi_table.json]

既定の stubs は tools/python/work/fl-stubs (fetch_inputs.sh が作る)。出力は 1 関数 1 行:
  関数 | 表の個数/PE max | stub 宣言 (ファイル:行・同名の定義数) | 分類 | PE kwlist (先頭 6)
分類は機械的な規則だけで付ける (PE 側と stub 側のどちらが正かは判定しない):
  可変長       : stub が *args で個数を宣言していない (表の個数は 0)
  オーバロード : 同名の def が複数あり、生成器は最後の定義だけを採る
  stub 少      : stub の引数が PE の max より少ない
  stub 多      : stub の引数が PE の max より多い
"""
import ast
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "flapi_table.json")
STUBS = os.environ.get("FL_STUBS_DIR") or os.path.join(HERE, "..", "..", "work", "fl-stubs")
BASE = os.path.join(STUBS, "src/midi_controller_scripting")

table = json.load(open(TABLE))
defs = defaultdict(list)  # (module, name) -> [(file, line, vararg, nparams)]
for m in table["modules"]:
    d = os.path.join(BASE, m)
    if not os.path.isdir(d):
        continue
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".py"):
            continue
        for node in ast.parse(open(os.path.join(d, fn)).read()).body:
            if isinstance(node, ast.FunctionDef):
                a = node.args
                defs[(m, node.name)].append((fn, node.lineno, a.vararg is not None, len(a.posonlyargs + a.args)))

rows = []
for m, fs in table["modules"].items():
    for n, e in fs.items():
        kw, sig = e.get("kwsig") or {}, e.get("sig")
        if kw.get("max") is None or not sig or len(sig["params"]) == kw["max"]:
            continue
        ds = defs.get((m, n), [])
        last = ds[-1] if ds else None
        if last and last[2]:
            cls = "可変長"
        elif len(ds) > 1:
            cls = "オーバロード"
        elif len(sig["params"]) < kw["max"]:
            cls = "stub 少"
        else:
            cls = "stub 多"
        where = f"{last[0]}:{last[1]}" if last else "-"
        kwl = ",".join(kw.get("kwlist", [])[:6]) or "-"
        rows.append(f"{m}.{n} | {len(sig['params'])}/{kw['max']} | {where} (def {len(ds)} 件) | {cls} | {kwl}")
print("関数 | 表の個数/PE max | stub 宣言 | 分類 | PE kwlist (先頭 6)")
print("---|---|---|---|---")
print("\n".join(rows))
print(f"不一致 {len(rows)} 件")
