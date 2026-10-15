#!/usr/bin/env python3
"""PY-257 子 (#3891): 0x1046a30 の mov+and+cmp+jcc の判定 5 件の立ち側・落ち側の作用を集計する (実機不要)。

  python3 analysis/py3891_and_cmp_jcc.py <PE.bin> <work/py53/fn.txt> <outdir>

判定箇所 = `mov eax, [rbp+0x5c0]` → `and eax, M` → `cmp eax, M` → 直後の jcc。
対象は analysis/py257_r8d_bits.py の `test eax, M` (173 件) の外にある形。
  jne : (M のビットが全部立つ) か否か。全立ち = fall-through (立ち)・一部落ち = 分岐先 (落ち)。
作用の経路は REPORT_PY257.md §2 と同じ (chain): fall-through と無条件 jmp を辿り、条件 jcc は分岐先を辿らない。
同じ計算を objdump (intel) の逆アセンブルで独立に行い、判定箇所と経路の記録を照合する (mismatch 0 で exit 0)。
出力: <outdir>/and_cmp_sites.tsv (判定ごとに両側の行)・<outdir>/and_cmp_join.md (両側の合流点)。
"""
import os
import sys

from py257_r8d_bits import chain, fmt_end, load_objdump, norm
from py64_branch_regions import load

HEAD = ("site", "mask", "jcc_va", "jcc", "side", "entry", "n_instr", "end", "end_src",
        "writes", "calls", "edges", "early_exit", "open_jcc", "tail_src")


def sites(ins, nxt):
    out = []
    for a in sorted(ins):
        mn, ops = ins[a]
        if mn != "mov" or norm(ops) != "eax,dwordptr[rbp+0x5c0]":
            continue
        b = nxt.get(a)
        if b is None or b not in ins or ins[b][0] != "and" or not norm(ins[b][1]).startswith("eax,"):
            continue
        c = nxt.get(b)
        if c is None or c not in ins or ins[c][0] != "cmp" or norm(ins[c][1]) != norm(ins[b][1]):
            continue
        j = nxt.get(c)
        if j is None or j not in ins or ins[j][0] != "jne":
            continue
        out.append((a, int(norm(ins[b][1]).split(",")[1], 0), j, ins[j][1]))
    return out


def rows_for(ins, nxt):
    out = []
    for tva, mask, jva, jops in sites(ins, nxt):
        tgt = int(jops.split()[0], 16)
        for lab, entry in (("立ち", nxt[jva]), ("落ち", tgt)):
            c = chain(ins, nxt, entry)
            out.append((
                f"{tva:#x}", f"{mask:#x}", f"{jva:#x}", "jne", lab, f"{entry:#x}", str(c["n"]),
                fmt_end(c["end"]), f"{c['src']:#x}" if c["src"] is not None else "-",
                ";".join(c["writes"]), ";".join(c["calls"]),
                ";".join(f"{a:#x}->{t:#x}" for a, t in c["edges"]), str(len(c["early"])),
                ";".join(f"{a:#x}" for a in c["open_jcc"]) or "-", c["tail_src"],
            ))
    return out


def main():
    pe_path, fn_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    cap_ins, cap_nxt = load(fn_path)
    ob_ins, ob_nxt = load_objdump(pe_path)
    cap_rows = rows_for(cap_ins, cap_nxt)
    ob_rows = rows_for(ob_ins, ob_nxt)

    mismatch = abs(len(cap_rows) - len(ob_rows))
    for x, y in zip(cap_rows, ob_rows):
        if x != y:
            mismatch += 1
            print(f"MISMATCH site={x[0]} side={x[4]} cols={[HEAD[i] for i in range(len(x)) if x[i] != y[i]]}")

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "and_cmp_sites.tsv"), "w") as f:
        f.write("\t".join(HEAD) + "\n")
        for r in ob_rows:
            f.write("\t".join(r) + "\n")

    print(f"sites={len(sites(ob_ins, ob_nxt))} rows={len(ob_rows)} cap_rows={len(cap_rows)} mismatch={mismatch}")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
