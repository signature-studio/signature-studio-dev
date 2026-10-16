#!/usr/bin/env python3
"""SR-94 #5612 (SR-82 #4930 受入 1 の子): ARG / ARG-CHILD の所属関数 F への vtable 経由の呼出元で、
F に渡す引数 (rdx/r8/r9) の出所を分類する (静的)。

入力: Serum2_win64.vst3 (PE)。trace.tsv (receiver_this_trace.py --tsv 出力)・vt_ind.tsv (arg_vt_indirect.py --tsv 出力)。
方法:
  1. vt_ind.tsv で、呼出元が SerumController (R.SC) の関数に候補 (n_sites_sc > 0) がある F と disp を取る。
  2. .text 内の SC 関数の `call qword ptr [reg + disp]` で disp が一致するものを列挙する (arg_vt_indirect と同じ照合)。
  3. 各候補 call の rdx/r8/r9 を後ろ向きに遡り、receiver_this_trace.py の origin / category で分類する。
出力は「候補」であり確定ではない。宛先 F は disp だけで照合しているため、受け手 (reg) の型が
F の所属 class かは未確定。よって確定件数は 0 のまま。
限界: 宛先の型 (reg の指す object) は見ない。THIS / THIS-EMB の分類は呼出元 C の this が SC である前提に依る。
usage: arg_vt_args.py <pe> <trace.tsv> <vt_ind.tsv> [--tsv out.tsv]
"""
import contextlib
import io
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ARGS = sys.argv
pe_path, tsv_trace, tsv_vt = ARGS[1], ARGS[2], ARGS[3]
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None

sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R

REGS = ("rdx", "r8", "r9")
ind_re = re.compile(r"qword ptr \[(\w+)(?: \+ (0x[0-9a-f]+|\d+))?\]")

trace_rows = []
with open(tsv_trace) as f:
    next(f)
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if cols[4] in ("vptr:ARG", "vptr:ARG-CHILD"):
            trace_rows.append((cols[4], int(cols[1], 16)))

cand_disp = defaultdict(set)
with open(tsv_vt) as f:
    next(f)
    for line in f:
        c = line.rstrip("\n").split("\t")
        if int(c[5]) > 0:
            cand_disp[int(c[0], 16)].add(int(c[3], 16))

rows = []
for ins in R.ins_all:
    if ins.mnemonic != "call":
        continue
    m = ind_re.search(ins.op_str)
    if not m:
        continue
    d = m.group(2) or "0"
    disp = int(d, 16) if d.startswith("0x") else int(d, 10)
    C = R.func_of(ins.address)
    if C not in R.SC:
        continue
    Fs = sorted(F for F, ds in cand_disp.items() if disp in ds)
    if not Fs:
        continue
    fn = R.get_fn(C)
    i = fn.index[ins.address]
    for F in Fs:
        for reg in REGS:
            s_root, s_steps = R.origin(fn, i, reg, True)
            l_root, l_steps = R.origin(fn, i, reg, False)
            s_cat = R.category(s_root, s_steps)
            l_cat = R.category(l_root, l_steps)
            rows.append((F, ins.address, C, disp, reg, s_cat, l_cat,
                         s_root + "".join(s_steps), l_root + "".join(l_steps)))

n_sites = len({(r[1]) for r in rows})
print(f"ARG 系 F への vtable 候補 (呼出元 SC・disp 一致) の call 箇所 = {n_sites} 件 / 対 (F, call, reg) = {len(rows)} 件")
agg_s = Counter(r[5] for r in rows)
agg_l = Counter(r[6] for r in rows)
print("strict 分類 (reg 単位):", dict(agg_s))
print("loose 分類 (reg 単位):", dict(agg_l))
sc_this_s = {r[1] for r in rows if r[5] in ("THIS", "THIS-EMB")}
sc_this_l = {r[1] for r in rows if r[6] in ("THIS", "THIS-EMB")}
print(f"引数 (rdx/r8/r9) の少なくとも 1 つが SC の this と分類された call 箇所: strict {len(sc_this_s)} 件 / loose {len(sc_this_l)} 件 (宛先 F は未確定)")

cand_F = {r[0] for r in rows}
per_row = Counter()
for cat, F in trace_rows:
    per_row[(cat, "候補あり" if F in cand_F else "候補なし")] += 1
for k in sorted(per_row):
    print(f"trace 行 {k[0]} / {k[1]}: {per_row[k]} 件")
print(f"trace 行の総数 {len(trace_rows)} 件 / 候補ありの F 数 {len(cand_F)} 個")
if TSV:
    with open(TSV, "w") as fh:
        fh.write("func\tcall_va\tcaller\tdisp\treg\tcat_strict\tcat_loose\tpath_strict\tpath_loose\n")
        for F, cva, C, disp, reg, sc, lc, ps, pl in rows:
            fh.write(f"{F:#x}\t{cva:#x}\t{C:#x}\t{disp:#x}\t{reg}\t{sc}\t{lc}\t{ps}\t{pl}\n")
