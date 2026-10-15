#!/usr/bin/env python3
"""SR-60 #4164: ARG / ARG-CHILD の所属関数 F の、直接 call の呼出元で、F に渡す引数 (rdx/r8/r9) の出所を分類する (静的)。

入力: Serum2_win64.vst3 (PE)。trace.tsv (receiver_this_trace.py --tsv 出力)。
方法: F への直接 call (call 0xF) ごとに、呼出元 C の call 位置で rdx/r8/r9 を後ろ向きに遡る (receiver_this_trace.py の origin を再利用)。
  分類は receiver_this_trace.py の category に従う。THIS / THIS-EMB は C の this そのもの (または埋め込み) なので、
  C が SerumController の関数 (sc_closure の集合 SC) なら、その引数は SerumController の候補。
  THIS-CHILD は C の this の子で、型は未確定。
限界: 間接 call (vtable 経由) の呼出元は見ない (宛先 F を静的に確定できないため)。
      rdx/r8/r9 の出所が THIS でも、F 側の型の証明にはならない (呼出元の this が SC であることは SC 伝播の範囲に依る)。
usage: arg_caller_types.py <pe> <trace.tsv> [--tsv out.tsv]
"""
import contextlib
import io
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ARGS = sys.argv
pe_path, tsv_in = ARGS[1], ARGS[2]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None

sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R

targets = set()
with open(tsv_in) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in ("vptr:ARG", "vptr:ARG-CHILD"):
            targets.add(int(cols[1], 16))

calls = defaultdict(list)
for ins in R.ins_all:
    if ins.mnemonic != "call" or not ins.op_str.startswith("0x"):
        continue
    try:
        t = int(ins.op_str, 16)
    except ValueError:
        continue
    if t in targets:
        calls[t].append(ins)

REGS = ("rdx", "r8", "r9")
rows = []
per_f = {}
for F in sorted(targets):
    sites = calls.get(F, [])
    cnt_sc_site = 0
    cats = Counter()
    for ins in sites:
        C = R.func_of(ins.address)
        if C is None:
            cats["NOFUNC"] += 1
            rows.append((F, ins.address, C, "-", "NOFUNC", "", "-"))
            continue
        fn = R.get_fn(C)
        i = fn.index[ins.address]
        ev = "S" if C in R.slot_fns else "K" if C in R.ctor_fns else "C" if C in R.SC else "-"
        in_sc = C in R.SC
        best = None
        for reg in REGS:
            root, steps = R.origin(fn, i, reg, True)
            cat = R.category(root, steps)
            cats[f"{reg}:{cat}"] += 1
            rows.append((F, ins.address, C, reg, cat, root + "".join(steps), ev))
            if cat in ("THIS", "THIS-EMB") and in_sc:
                best = reg
        if best:
            cnt_sc_site += 1
    per_f[F] = (len(sites), cnt_sc_site, cats)

n_f = len(targets)
n_sites = sum(v[0] for v in per_f.values())
n_f_called = sum(1 for v in per_f.values() if v[0])
n_f_sc = sum(1 for v in per_f.values() if v[1])
n_sites_sc = sum(v[1] for v in per_f.values())
print(f"ARG 系の所属関数 = {n_f} 個 / 直接 call の呼出元がある = {n_f_called} 個 / 呼出元 call 数 = {n_sites}")
print(f"呼出元が SerumController の関数で、rdx/r8/r9 のいずれかが SC の this (THIS/THIS-EMB) の呼出 = {n_sites_sc} 件 (所属関数 {n_f_sc} 個)")
agg = Counter()
for v in per_f.values():
    agg.update(v[2])
for k, n in sorted(agg.items(), key=lambda x: -x[1])[:25]:
    print(f"{n:5d}  {k}")
if TSV:
    with open(TSV, "w") as fh:
        fh.write("func\tcall_va\tcaller\treg\tcat\tpath\tcaller_evidence\n")
        for F, cva, C, reg, cat, path, ev in rows:
            fh.write(f"{F:#x}\t{cva:#x}\t{(C or 0):#x}\t{reg}\t{cat}\t{path}\t{ev}\n")
