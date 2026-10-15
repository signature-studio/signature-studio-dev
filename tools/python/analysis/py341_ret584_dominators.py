#!/usr/bin/env python3
"""PY-341 (#4574): `[rbp+0x5b8]` の直接書込みごとに、関数入口から書込みまでの全経路が必ず通る分岐 (支配関係) を出す。

  python3 analysis/py341_ret584_dominators.py <work/py53/fn.txt> <outdir>

出力: <outdir>/ret584_dominators.tsv (書込み 1 件 1 行)
  write_VA・source・dom_depth (入口からの支配木の深さ)・forced (必ず通る分岐: VA・jcc・立ち/落ち・直前のフラグ設定命令)
全経路の列挙は指数的に増えるため行わない (単純パス列挙は 72 件中 73 件で上限に達した: REPORT_PY41_3860.md §5)。
支配関係は「その分岐の一方の辺だけが書込みへの全経路を通る」場合にだけ確定値として出す。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from py262_ret584_paths import ENTRY, WRITE_OP, edges, flag_setter, load  # noqa: E402


def rpo_and_preds(out, entry):
    seen, post = set([entry]), []
    stack = [(entry, iter(out.get(entry, [])))]
    while stack:
        v, it = stack[-1]
        for w, _ in it:
            if w not in seen:
                seen.add(w)
                stack.append((w, iter(out.get(w, []))))
                break
        else:
            post.append(v)
            stack.pop()
    rpo = list(reversed(post))
    pred = {v: [] for v in rpo}
    for v in rpo:
        for w, _ in out.get(v, []):
            if w in pred:
                pred[w].append(v)
    return rpo, pred


def idoms(rpo, pred, entry):
    num = {v: i for i, v in enumerate(rpo)}
    idom = {entry: entry}

    def intersect(a, b):
        while a != b:
            while num[a] > num[b]:
                a = idom[a]
            while num[b] > num[a]:
                b = idom[b]
        return a

    changed = True
    while changed:
        changed = False
        for v in rpo[1:]:
            ps = [p for p in pred[v] if p in idom]
            if not ps:
                continue
            new = ps[0]
            for p in ps[1:]:
                new = intersect(p, new)
            if idom.get(v) != new:
                idom[v] = new
                changed = True
    return idom


def reach_without_edge(out, entry, target, bd, bs):
    """辺 bd->bs を除いたとき entry から target に到達できるか。"""
    seen, q = {entry}, [entry]
    while q:
        v = q.pop()
        if v == target:
            return True
        for w, _ in out.get(v, []):
            if v == bd and w == bs:
                continue
            if w not in seen:
                seen.add(w)
                q.append(w)
    return False


def main():
    ins, order = load(sys.argv[1])
    outdir = sys.argv[2]
    out = edges(ins, order)
    rpo, pred = rpo_and_preds(out, ENTRY)
    idom = idoms(rpo, pred, ENTRY)
    writes = [va for va in order if ins[va][0] == "mov" and ins[va][1].startswith(WRITE_OP)]
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "ret584_dominators.tsv")
    n_done = 0
    with open(path, "w") as f:
        f.write("write_VA\tsource\tdom_depth\tforced\n")
        for w in writes:
            if w not in idom:
                continue
            chain, v = [], w
            while v != ENTRY:
                chain.append(v)
                v = idom[v]
            chain.append(ENTRY)
            chain.reverse()
            forced = []
            for d in chain:
                mn, op = ins[d]
                if not mn.startswith("j") or mn == "jmp":
                    continue
                for s, lab in out.get(d, []):
                    if not reach_without_edge(out, ENTRY, w, d, s):
                        forced.append(f"{d:#x} {mn}({lab}) after [{flag_setter(ins, order, d)}]")
            f.write(f"{w:#x}\t{ins[w][1]}\t{len(chain) - 1}\t{'; '.join(forced) or '(必ず通る分岐なし)'}\n")
            n_done += 1
    print(f"writes={len(writes)} reachable={n_done} wrote={path}")


if __name__ == "__main__":
    main()
