#!/usr/bin/env python3
"""SR-82 #4930 受入 1: arg_vt_indirect の候補のうち、呼出元が SC の関数の call [reg+disp] について、
受け手 (reg の指す object) の出所を receiver_this_trace.receiver() で分類する (strict / loose)。
usage: recv_sc_sites.py <pe> <vt_ind.tsv>
"""
import contextlib
import os
import io
import sys
from collections import Counter, defaultdict


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pe_path, vt_tsv = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R
import re

ind_re = re.compile(r"qword ptr \[(\w+)(?: \+ (0x[0-9a-f]+|\d+))?\]")
disps = set()
with open(vt_tsv) as f:
    next(f)
    for line in f:
        c = line.rstrip("\n").split("\t")
        if int(c[5]) > 0:
            disps.add(int(c[3], 16))

out = Counter()
rows = []
for ins in R.ins_all:
    if ins.mnemonic != "call":
        continue
    m = ind_re.search(ins.op_str)
    if not m:
        continue
    d = m.group(2) or "0"
    disp = int(d, 16) if d.startswith("0x") else int(d, 10)
    if disp not in disps:
        continue
    f = R.func_of(ins.address)
    if f not in R.SC:
        continue
    fn = R.get_fn(f)
    i = fn.index[ins.address]
    res = {}
    for strict in (True, False):
        mode, root, steps = R.receiver(fn, i, m.group(1), strict)
        res[strict] = (mode, root, steps)
    rows.append((ins.address, f, disp, res[True], res[False]))
    out[("strict", res[True][0], res[True][1], "".join(res[True][2]))] += 1
    out[("loose", res[False][0], res[False][1], "".join(res[False][2]))] += 1

print(f"SC 関数内の候補 call = {len(rows)} 件")
for k, v in sorted(out.items(), key=lambda x: -x[1]):
    print(v, k)
for a, f, disp, s, l in rows:
    print(f"{a:#x}\tfunc={f:#x}\tdisp={disp:#x}\tstrict={s[0]}:{s[1]}{''.join(s[2])}\tloose={l[0]}:{l[1]}{''.join(l[2])}")
