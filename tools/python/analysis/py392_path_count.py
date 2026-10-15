#!/usr/bin/env python3
"""PY-392 (#4828): `[rbp+0x5b8]` の直接書込みのうち 0x104cc65 に届くものについて、
関数入口から書込み w に至る DAG 上の経路数 (prefix) と、w から 0x104cc65 へ別の書込みを挟まずに至る経路数 (suffix) を
大整数の DP で数える。書込み w 1 件あたりの経路数は prefix * suffix (入口 → w → TARGET の全経路・w を通るもの)。

  python3 analysis/py392_path_count.py <work/py53/fn.txt> <outdir>

方式は py392_ret584_suffcond.py と同じ辺 (後ろ向きの辺は外す)。BDD を使わないため変数順序に依存しない。
出力: <outdir>/path_count.tsv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from py262_ret584_paths import ENTRY, WRITE_OP, edges, load  # noqa: E402
from py341_ret584_dominators import rpo_and_preds  # noqa: E402

TARGET = 0x104CC65


def main():
    ins, order = load(sys.argv[1])
    outdir = sys.argv[2]
    out = edges(ins, order)
    rpo, _ = rpo_and_preds(out, ENTRY)
    pos = {v: i for i, v in enumerate(rpo)}
    writes = [va for va in order if ins[va][0] == "mov" and ins[va][1].startswith(WRITE_OP)]
    wset = set(writes)

    def fwd(v):
        return [s for s, _ in out.get(v, []) if s in pos and pos[s] > pos[v]]

    # prefix: 入口から v への DAG 上の経路数 (別書込みを通ってよい)
    P = {v: 0 for v in rpo}
    P[ENTRY] = 1
    for v in rpo:
        if P[v] == 0:
            continue
        for s in fwd(v):
            P[s] += P[v]

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "path_count.tsv")
    n = n_live = 0
    with open(path, "w") as f:
        f.write("write_VA\tsource\tprefix_paths_to_write\tsuffix_paths_to_target_no_write\troutes_through_write\n")
        for w in writes:
            if w not in pos:
                continue
            n += 1
            # S: v から TARGET へ、途中で別の書込み (w 以外) を通らない経路数 (逆向き DP)
            S = {v: 0 for v in rpo}
            S[TARGET] = 1
            for v in reversed(rpo):
                if v == TARGET:
                    continue
                if v in wset and v != w:
                    continue
                S[v] = sum(S[s] for s in fwd(v) if not (s in wset and s != TARGET and s != w))
            # w の先は w 自身の書込みで止まらない。w の後続だけを数える
            suffix = sum(S[s] for s in fwd(w) if not (s in wset and s != TARGET))
            routes = P[w] * suffix
            if suffix:
                n_live += 1
            f.write(f"{w:#x}\t{ins[w][1]}\t{P[w]}\t{suffix}\t{routes}\n")
    print(f"writes_in_rpo={n} reach_target_no_intervening_write={n_live} wrote={path}")


if __name__ == "__main__":
    main()
