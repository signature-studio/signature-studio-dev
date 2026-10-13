"""SR-19 #1351: GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築の対象量を実測する。

入力: work/uidesc.json (extract_uidesc.py の出力) / work/vstgui4 (vstgui4_14_3 の clone, depth 1)
出力: stdout (work/effort_measure.txt に保存して REPORT_EFFORT.md の根拠にする)
工数 (人日) はここでは測らない。対象量のみ。
"""
import collections
import json
import os
import re
import subprocess
import sys

UIDESC = sys.argv[1] if len(sys.argv) > 1 else "work/uidesc.json"
VSTGUI = sys.argv[2] if len(sys.argv) > 2 else "work/vstgui4/vstgui"

d = json.load(open(UIDESC, encoding="utf-8"))["vstgui-ui-description"]
cls = collections.Counter()
keys = collections.defaultdict(set)
sub = collections.Counter()
tpl_classes = {}
tpl_subs = {}


def walk(n, acc, subs):
    if isinstance(n, dict):
        if "class" in n:
            c = n["class"]
            cls[c] += 1
            acc.add(c)
            keys[c].update(n.keys())
        if "sub-controller" in n:
            sub[n["sub-controller"]] += 1
            subs.add(n["sub-controller"])
        for v in n.values():
            walk(v, acc, subs)
    elif isinstance(n, list):
        for v in n:
            walk(v, acc, subs)


for name, body in d["templates"].items():
    a, s = set(), set()
    walk(body, a, s)
    tpl_classes[name] = a
    tpl_subs[name] = s

files = subprocess.run(
    f"find {VSTGUI} -path '*/tests/*' -prune -o \\( -name '*.h' -o -name '*.cpp' -o -name '*.mm' \\) -print",
    shell=True, capture_output=True, text=True).stdout.split()
_up = {}


def upstream_has(name):
    if name not in _up:
        r = subprocess.run(["grep", "-rwlE", rf"(class|struct) {name}\b"] + files,
                           capture_output=True, text=True)
        _up[name] = bool(r.stdout.split())
    return _up[name]


def is_c(name):
    return name.startswith("C") and name[1:2].isupper()


print("== (uidesc) ==")
print("templates:", len(d["templates"]), "bitmaps:", len(d["bitmaps"]))
print("view class refs:", sum(cls.values()), "distinct:", len(cls))
yes = [c for c in cls if upstream_has(c)]
no = [c for c in cls if not upstream_has(c)]
print("  declared in upstream 14.3:", len(yes), "distinct /", sum(cls[c] for c in yes), "refs")
print("  not declared in upstream 14.3 (Xfer 固有・置換対象):", len(no), "distinct /", sum(cls[c] for c in no), "refs")
print("  C-prefixed but not upstream:", sorted(c for c in no if is_c(c)))
print("  xfer attribute keys (union over no-list):", len({k for c in no for k in keys[c]}))
print("sub-controller refs:", sum(sub.values()), "distinct:", len(sub),
      "declared in upstream:", sum(1 for s in sub if upstream_has(s)))

pure = [t for t in tpl_classes if all(upstream_has(c) for c in tpl_classes[t]) and not tpl_subs[t]]
print("templates using only upstream classes and no sub-controller:", len(pure), "of", len(d["templates"]))
print("  names:", sorted(pure))
touch_xfer = [t for t in tpl_classes if any(not upstream_has(c) for c in tpl_classes[t]) or tpl_subs[t]]
print("templates touching >=1 Xfer class or sub-controller:", len(touch_xfer), "of", len(d["templates"]))

print("== (PoC 境界の uidesc 側) ==")
for c in ("CTextLabel", "XferOnOffButton"):
    print(f"{c}: refs {cls[c]}, distinct attribute keys {len(keys[c])}")
poc_only = [t for t in tpl_classes if tpl_classes[t] and tpl_classes[t] <= {"CTextLabel", "XferOnOffButton", "CViewContainer"} and not tpl_subs[t]]
print("templates using only {CTextLabel, XferOnOffButton, CViewContainer} and no sub-controller:", len(poc_only), sorted(poc_only)[:10])

print("== (upstream 14.3) ==")
src_all = subprocess.run(f"find {VSTGUI} -path '*/tests/*' -prune -o \\( -name '*.cpp' -o -name '*.h' -o -name '*.mm' \\) -print0 | xargs -0 cat | wc -lc",
                         shell=True, capture_output=True, text=True).stdout.strip()
src_plat = subprocess.run(f"find {VSTGUI} -path '*/tests/*' -prune -o -path '*/platform/*' \\( -name '*.cpp' -o -name '*.h' -o -name '*.mm' \\) -print0 | xargs -0 cat | wc -lc",
                          shell=True, capture_output=True, text=True).stdout.strip()
print("non-test cpp/h/mm (lines, bytes):", src_all)
print("  of which platform/ (lines, bytes):", src_plat)
print("uidescription/viewcreator-related files:",
      len([f for f in files if "uidescription" in f]))
