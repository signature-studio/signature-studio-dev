#!/usr/bin/env python3
"""lift 出力 (fle_lifted.c) の基本ブロック先頭 (L_<VA>: ラベル) に到達計測 wc_cov(i) を入れる (T-SH-115 / #4303)。
出力: WORKDIR/blocks.txt (i 行目 = ブロック i の RVA 16 進)、WORKDIR/dataref.txt (.data を指す textref の RVA)。
usage: wc_cov_inject.py WORKDIR     (WORKDIR/lift/fle_lifted.c と lift_meta.json・layout.json を読み、fle_lifted.c を書き換える)
"""
import json, re, sys
W = sys.argv[1]
SRC = f"{W}/lift/fle_lifted.c"
IMG = 0x180000000
src = open(SRC).read()
labels = []
seen = set()
for m in re.finditer(r"^(L_([0-9a-f]+)):", src, re.M):
    va = int(m.group(2), 16)
    if va not in seen:
        seen.add(va)
        labels.append(va)
idx = {va: i for i, va in enumerate(labels)}
out = re.sub(r"^(L_([0-9a-f]+)):", lambda m: f"{m.group(1)}: wc_cov({idx[int(m.group(2), 16)]});", src, flags=re.M)
open(SRC, "w").write(out.replace('#include "fle_cpu.h"\n', '#include "fle_cpu.h"\nvoid wc_cov(uint32_t);\n', 1))
open(f"{W}/blocks.txt", "w").write("".join(f"{va - IMG:x}\n" for va in labels))
L = json.load(open(f"{W}/layout.json"))
meta = json.load(open(f"{W}/lift/lift_meta.json"))
d0, dsz = L["data_rva"], L["data_sz"]
refs = sorted({a - IMG for a in meta["textrefs"] if d0 <= a - IMG < d0 + dsz})
open(f"{W}/dataref.txt", "w").write("".join(f"{r:x}\n" for r in refs))
print(f"[wc_cov] blocks={len(labels)} data_refs={len(refs)}")
if len(labels) > 512:
    sys.exit("[wc_cov] blocks > 512 (wc_covb の大きさを超える)")
