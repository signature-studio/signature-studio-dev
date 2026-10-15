#!/usr/bin/env python3
"""PY-392 (#4828): `[rbp+0x5b8]` の直接書込みのうち 0x104cc65 に届くものについて、
関数入口からその書込みに至る経路の十分条件 (jcc の立ち/落ちの論理式) を BDD で求める。

  python3 analysis/py392_ret584_suffcond.py <work/py53/fn.txt> <outdir>

方式:
- 辺は py262_ret584_paths.edges() と同じ (jcc の立ち = 変数が真・落ち = 偽)。
- 後ろ向きの辺 (ループ) は外す。各経路は各ノードを高々 1 回通るため、変数 (jcc の VA) の値が
  経路内で矛盾しない。よって出力の式の各充足割当は、実在しうる非ループ経路に対応する。
- R(entry)=真、R(v)=OR_p (R(p) AND 辺 p->v の条件) を RPO 順に畳み込む。
- 出力: <outdir>/suffcond.tsv (書込み 1 件 1 行: VA・出どころ・BDD ノード数・cube 数・式)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from py262_ret584_paths import ENTRY, WRITE_OP, edges, load  # noqa: E402
from py341_ret584_dominators import rpo_and_preds  # noqa: E402
from dd.autoref import BDD  # noqa: E402

TARGET = 0x104CC65


def disjoint_paths(u):
    """BDD の 1 への経路数 (経路どうしは排他的な割当の集合)。"""
    memo = {}

    def rec(x):
        if x.node in memo:
            return memo[x.node]
        if x == x.bdd.true:
            r = 1
        elif x == x.bdd.false:
            r = 0
        else:
            r = rec(x.high) + rec(x.low)
        memo[x.node] = r
        return r

    return rec(u)


def main():
    ins, order = load(sys.argv[1])
    outdir = sys.argv[2]
    out = edges(ins, order)
    rpo, _ = rpo_and_preds(out, ENTRY)
    pos = {v: i for i, v in enumerate(rpo)}
    jcc = [v for v in rpo if ins[v][0].startswith("j") and ins[v][0] != "jmp"]
    bdd = BDD()
    names = [f"j{v:x}" for v in jcc]
    bdd.declare(*names)
    var = {v: bdd.var(f"j{v:x}") for v in jcc}
    var_of = {f"j{v:x}": var[v] for v in jcc}
    def cond(v, lab):
        if ins[v][0].startswith("j") and ins[v][0] != "jmp":
            return var[v] if lab == "立ち" else ~var[v]
        return bdd.true

    R = {v: bdd.false for v in rpo}
    R[ENTRY] = bdd.true
    for v in rpo:
        if R[v] == bdd.false:
            continue
        for w, lab in out.get(v, []):
            if w not in pos or pos[w] <= pos[v]:
                continue
            R[w] = R[w] | (R[v] & cond(v, lab))
    writes = [va for va in order if ins[va][0] == "mov" and ins[va][1].startswith(WRITE_OP)]
    wset = set(writes)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "suffcond.tsv")
    n = n_live = 0
    with open(path, "w") as f:
        f.write("write_VA\tsource\tentry_cond_dag_size\tlive_cond_dag_size\tvars_in_cond\tbdd_1_paths\tlive\tcube_lits\tcube\n")
        for w in writes:
            if w not in pos:
                continue
            n += 1
            # G: w の後、別の書込みを挟まずに TARGET へ届く条件 (逆向き DP、DAG 上)
            G = {v: bdd.false for v in rpo}
            G[TARGET] = bdd.true
            for v in reversed(rpo):
                if v == TARGET or v == w:
                    continue
                if v in wset:
                    continue
                acc = bdd.false
                for s, lab in out.get(v, []):
                    if s not in pos or pos[s] <= pos[v] or s in wset and s != TARGET:
                        continue
                    c = cond(v, lab)
                    acc = acc | (c & G[s])
                G[v] = acc
            acc = bdd.false
            for s, lab in out.get(w, []):
                if s not in pos or pos[s] <= pos[w] or (s in wset and s != TARGET):
                    continue
                acc = acc | (cond(w, lab) & G[s])
            live = R[w] & acc
            reach = live != bdd.false
            n_live += reach
            paths = disjoint_paths(live) if reach else 0
            ent = R[w].dag_size if R[w] != bdd.false else 0
            sup = len([s for s in live.support if s.startswith("j")]) if reach else 0
            cube = live.pick() if reach else None
            if reach:
                lit = bdd.true
                for k, val in cube.items():
                    lit = lit & (var_of[k] if val else ~var_of[k])
                if (lit & ~live) != bdd.false:
                    raise SystemExit(f"not an implicant: {w:#x}")
            expr = "(なし)" if not reach else " & ".join(
                f"{k[1:]}{'' if val else '!'}" for k, val in sorted(cube.items())) or "1"
            f.write(f"{w:#x}\t{ins[w][1]}\t{ent}\t{live.dag_size if reach else 0}\t{sup}\t{paths}\t{reach}\t{len(cube or {})}\t{expr}\n")
    print(f"writes_in_rpo={n} live_to_target={n_live} vars={len(names)} wrote={path}")


if __name__ == "__main__":
    main()
