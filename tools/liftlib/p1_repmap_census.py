#!/usr/bin/env python3
"""p1_repmap_census.py — legacy_p1 の repmap 適用件数を測る (#3067)。

  python3 p1_repmap_census.py [IR] [--module <p1_legacy.py>]

  IR       省略時 tools/m6/work/ott_lift.ll (挿入前の OTT lift IR)
  --module 比較する p1_legacy.py のパス (省略時は liftlib.passes.p1_legacy)

出力 (JSON 1 行):
  entries      repmap の組数 (stats.hits から: br_cf+br_zf+br_pf+br_? + 2*(or_cfzf+or_zfcf))
  br_applied   書換え後の `br i1 %pcN<cf|zf|pf>` の本数 (期待 = br 系の組数)
  or_applied   書換え後の `or i1 %pcN.., %pcN..` の本数 (期待 = or 系の行数)
  double_pct   `%%pc` の出現数 (0 が正)
  br_residual  書換え後に残る `br i1 %<cf|zf|pf>.N` の本数 (comis 挿入の窓外の分岐は残る)
  diff_lines   入力と出力の差分 (difflib, 挿入行を除く) の変更行数 (期待 18 = br 17 + or 1)
  diff_removed 変更行から消えた旧名トークン `%<cf|zf|pf>.N` の数 (期待 19 = entries)
  diff_no_pc   変更行のうち `%pc` を含まない行 (0 が正)
"""
import difflib
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
mod_path = None
if "--module" in args:
    i = args.index("--module")
    mod_path = args[i + 1]
    del args[i:i + 2]
ir_path = args[0] if args else os.path.join(HERE, "..", "m6", "work", "ott_lift.ll")

if mod_path:
    spec = importlib.util.spec_from_file_location("p1_legacy_under_test", mod_path)
    p1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p1)
else:
    sys.path.insert(0, os.path.join(HERE))
    from liftlib.passes import p1_legacy as p1

text = open(ir_path).read()
out, st = p1.legacy_p1(text)
h = st["hits"]
entries = h.get("br_cf", 0) + h.get("br_zf", 0) + h.get("br_pf", 0) + h.get("br_?", 0) + 2 * (h.get("or_cfzf", 0) + h.get("or_zfcf", 0))
tok = re.compile(r"%(?:cf|zf|pf)\.\d+")
a, b = text.split("\n"), out.split("\n")
d_lines = d_removed = d_no_pc = 0
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
    if tag != "replace" or i2 - i1 != j2 - j1:
        continue
    for x, y in zip(a[i1:i2], b[j1:j2]):
        if x != y:
            d_lines += 1
            d_removed += len(tok.findall(x)) - len(tok.findall(y))
            d_no_pc += "%pc" not in y
res = {
    "entries": entries,
    "br_applied": len(re.findall(r"br i1 %pc\d+(?:cf|zf|pf)\b", out)),
    "or_applied": len(re.findall(r"= or i1 %pc\d+(?:cf|zf|pf), %pc\d+(?:cf|zf|pf)", out)),
    "double_pct": out.count("%%pc"),
    "br_residual": len(re.findall(r"br i1 %(?:cf|zf|pf)\.\d+", out)),
    "diff_lines": d_lines,
    "diff_removed": d_removed,
    "diff_no_pc": d_no_pc,
}
print(json.dumps(res, ensure_ascii=False))
