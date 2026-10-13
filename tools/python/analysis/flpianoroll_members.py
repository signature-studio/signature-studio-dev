"""flpianoroll の公開メンバ実装数を再計算する (PY-19 / #792)。

数え方の定義:
  * 母集団 = analysis/flapi/flapi_table.json の objects.flpianoroll.classes の全メンバ
    (Note 17 / Marker 7 / score(Pattern) 22 / Utils(TUtils) 3 / ScriptDialog 15 = 64)。
    `clone()` のような括弧付きは括弧を外して名前だけで判定する。
  * 実装 = src/flpianoroll.py を import した後、そのクラス/インスタンスに該当名の属性があること。
    score / Utils / ScriptDialog は Score() / TUtils() / ScriptDialog() のインスタンスで判定する
    (PPQ・tsnum 等はインスタンス属性、noteCount 等は property)。
  * 「stub」= 属性はあるが NotImplementedError を投げるもの。本スクリプトは呼び出さず、
    stub は grep (`NotImplementedError` in src/flpianoroll.py) で別途確認する。

実行: python3 analysis/flpianoroll_members.py [--json]   (終了コード 0 = 全件実装、1 = 未実装あり)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import flpianoroll as fp  # noqa: E402

table = json.load(open(os.path.join(HERE, "flapi", "flapi_table.json"), encoding="utf-8"))
classes = table["objects"]["flpianoroll"]["classes"] if "objects" in table else table["flpianoroll"]["classes"]

owner = {
    "Note": fp.Note(),
    "Marker": fp.Marker(),
    "score(Pattern)": fp.Score(),
    "Utils(TUtils)": fp.TUtils(),
    "ScriptDialog": fp.ScriptDialog(),
}
rows = []
for cls, members in classes.items():
    obj = owner[cls]
    for m in members:
        name = m[:-2] if m.endswith("()") else m
        rows.append({"class": cls, "member": m, "implemented": hasattr(obj, name)})

total = len(rows)
impl = sum(r["implemented"] for r in rows)
missing = [f'{r["class"]}.{r["member"]}' for r in rows if not r["implemented"]]
if "--json" in sys.argv:
    print(json.dumps({"total": total, "implemented": impl, "missing": missing}, ensure_ascii=False))
else:
    print(f"flpianoroll members: {impl}/{total} implemented")
    for x in missing:
        print("MISSING", x)
sys.exit(0 if impl == total else 1)
