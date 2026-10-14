#!/usr/bin/env python3
# B1 (patch_uninit_alloca) の 0 埋め件数の内訳を e.lift.ll から集計する ([PLG-F3-19] #2047)。
#   python3 dynamics/b1_measure.py <engine_out_dir>   例: work/dynamics/engine19252
# 検算 (別アルゴリズム): grep -c '= xor i64 0, 0$' の総数と関数別合計が一致すること。
import re
import sys

out = sys.argv[1] if len(sys.argv) > 1 else "work/dynamics/engine19252"
text = open(f"{out}/e.lift.ll").read()
rows = []
for part in re.split(r"\n(?=define )", text):
    if not part.startswith("define"):
        continue
    n = len(re.findall(r"= xor i64 0, 0\b", part))
    if n:
        name = re.search(r"@([\w$.]+)\(", part).group(1)
        rows.append((n, name))
rows.sort(reverse=True)
print(f"xor_i64_0 total={sum(n for n, _ in rows)} funcs={len(rows)}")
print("top10=" + ",".join(f"{nm}:{n}" for n, nm in rows[:10]))
print("function_180019c20=" + ",".join(f"{nm}:{n}" for n, nm in rows if nm == "function_180019c20"))
