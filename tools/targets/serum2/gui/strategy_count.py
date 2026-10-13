"""SR-7 #68: uidesc の View クラス / sub-controller を集計し、RTTI 照合の結果を出す。

入力: work/uidesc.json (extract_uidesc.py の出力) / out/rtti_classes.txt (REPORT §3)
出力: stdout (out/gui_strategy_count.txt に保存して使う)
"""
import collections
import json
import re
import sys

UIDESC = sys.argv[1] if len(sys.argv) > 1 else "work/uidesc.json"
RTTI = sys.argv[2] if len(sys.argv) > 2 else "out/rtti_classes.txt"

d = json.load(open(UIDESC, encoding="utf-8"))["vstgui-ui-description"]
cls = collections.Counter()
sub = collections.Counter()


def walk(n):
    if isinstance(n, dict):
        if "class" in n:
            cls[n["class"]] += 1
        if "sub-controller" in n:
            sub[n["sub-controller"]] += 1
        for v in n.values():
            walk(v)
    elif isinstance(n, list):
        for v in n:
            walk(v)


walk(d["templates"])
rtti = open(RTTI, encoding="utf-8", errors="replace").read()


def present(name):
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", rtti) is not None


c_prefixed = [c for c in cls if c.startswith("C") and c[1:2].isupper()]
print("templates:", len(d["templates"]), "bitmaps:", len(d["bitmaps"]))
print("view class refs:", sum(cls.values()), "distinct:", len(cls))
print("  in RTTI (name match):", sum(1 for c in cls if present(c)), "of", len(cls))
print("  C-prefixed (VSTGUI 標準名とみなす・ヒューリスティック):", len(c_prefixed), "distinct /", sum(cls[c] for c in c_prefixed), "refs")
print("  その他 (Xfer 独自とみなす・ヒューリスティック):", len(cls) - len(c_prefixed), "distinct /", sum(v for k, v in cls.items() if k not in c_prefixed), "refs")
print("sub-controller refs:", sum(sub.values()), "distinct:", len(sub))
print("  in RTTI (name match):", sum(1 for s in sub if present(s)), "of", len(sub))
print("  not in RTTI:", sorted(s for s in sub if not present(s)))
print("top 10 view classes:")
for c, n in cls.most_common(10):
    print(f"  {n:4d} {c}")
