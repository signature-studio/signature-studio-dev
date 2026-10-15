#!/usr/bin/env python3
"""SR-43 #2174: receiver_this_trace.py の判定点を 1 箇所ずつ壊した複製で strict 分類を再計算し、基準 TSV と比べる (ネガティブコントロール)。
usage: negctl_this_trace.py <pe> <baseline.tsv> <workdir>
出力: 判定点ごとに、cat_strict が変わった件数と、旧 -> 新の内訳 (上位 8)。
"""
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PE, BASE, WD = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
SRC = (HERE / "receiver_this_trace.py").read_text(encoding="utf-8")
MUTANTS = {
    "dominated-always-true": ("        if self.indirect:\n            return False\n        return u not in self.reach(d) and u in self.reach(-1)",
                              "        return True"),
    "argname-rcx-as-arg": ('ARGNAME = {"rcx": "this",', 'ARGNAME = {"rcx": "arg",'),
    "find-store-none": ("def find_store(fn, k, mem):\n", "def find_store(fn, k, mem):\n    return None\n"),
}


def read_tsv(path):
    rows = {}
    with open(path, encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            rows[f[0]] = f[4]
    return rows


WD.mkdir(parents=True, exist_ok=True)
base = read_tsv(BASE)
print(f"基準 {BASE.name}: {len(base)} 件 (THIS {sum(v == 'vptr:THIS' for v in base.values())})")
for name, (old, new) in MUTANTS.items():
    assert SRC.count(old) == 1, name
    mut, out = WD / f"mut_{name}.py", WD / f"mut_{name}.tsv"
    mut.write_text(SRC.replace(old, new), encoding="utf-8")
    subprocess.run([sys.executable, str(mut), PE, "--vtable", "0x180a2bf58", "--tsv", str(out)],
                   check=True, stdout=subprocess.DEVNULL)
    got = read_tsv(out)
    diff = Counter((base[k], got[k]) for k in base if base[k] != got[k])
    print(f"[{name}] 分類が変わった件数: {sum(diff.values())}/{len(base)} (THIS {sum(v == 'vptr:THIS' for v in got.values())})")
    for (a, b), c in diff.most_common(8):
        print(f"  {c:4d}  {a} -> {b}")
