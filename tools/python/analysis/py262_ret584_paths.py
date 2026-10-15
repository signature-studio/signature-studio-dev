#!/usr/bin/env python3
"""PY-262 (#3860): `[rbp+0x5b8]` の直接書込みごとに、関数入口からの代表経路 (CFG 上の最短 1 本) と、その経路上の分岐条件を出す。

  python3 analysis/py262_ret584_paths.py <work/py53/fn.txt> <outdir>

出力: <outdir>/ret584_paths.tsv (書込み 1 件 1 行: VA・命令・経路長・経路上の分岐 (VA・jcc・辺の立ち/落ち・直前のフラグ設定命令))
経路は path-insensitive な CFG 上の最短 1 本。同じ書込みに至る別経路の条件は含まない。
"""
import os
import re
import sys
from collections import deque

ADDR_RE = re.compile(r"(0x[0-9a-f]+): (\S+)\s*(.*)$")
ENTRY = 0x1046A30
WRITE_OP = "dword ptr [rbp + 0x5b8], "
FLAG_SET = ("cmp", "test", "and", "sub", "add", "or", "xor", "ucomisd", "comisd", "bt", "set")


def load(path):
    ins, order = {}, []
    for ln in open(path):
        m = ADDR_RE.match(ln.rstrip("\n"))
        if m:
            va = int(m.group(1), 16)
            ins[va] = (m.group(2), m.group(3).strip())
            order.append(va)
    return ins, order


def edges(ins, order):
    idx = {va: i for i, va in enumerate(order)}
    out = {}
    for i, va in enumerate(order):
        mn, op = ins[va]
        nxt = order[i + 1] if i + 1 < len(order) else None
        e = []
        m = re.match(r"(0x[0-9a-f]+)", op)
        tgt = int(m.group(1), 16) if m and mn.startswith("j") else None
        if mn == "ret":
            pass
        elif mn == "jmp":
            if tgt in idx:
                e.append((tgt, "-"))
        elif mn.startswith("j"):
            if tgt in idx:
                e.append((tgt, "立ち"))
            if nxt is not None:
                e.append((nxt, "落ち"))
        elif nxt is not None:
            e.append((nxt, "-"))
        out[va] = e
    return out


def flag_setter(ins, order, va):
    i = order.index(va)
    for k in range(i - 1, max(i - 8, -1), -1):
        mn, op = ins[order[k]]
        if mn.startswith(FLAG_SET):
            return f"{order[k]:#x} {mn} {op}"
    return "?"


def main():
    ins, order = load(sys.argv[1])
    outdir = sys.argv[2]
    out = edges(ins, order)
    prev = {ENTRY: None}
    q = deque([ENTRY])
    while q:
        v = q.popleft()
        for w, lab in out.get(v, []):
            if w not in prev:
                prev[w] = (v, lab)
                q.append(w)
    writes = [va for va in order if ins[va][0] == "mov" and ins[va][1].startswith(WRITE_OP)]
    rows = []
    for w in writes:
        if w not in prev:
            continue
        chain = []
        n = 0
        v = w
        while prev[v] is not None:
            p, lab = prev[v]
            if ins[p][0].startswith("j"):
                chain.append((p, ins[p][0], lab))
            v = p
            n += 1
        chain.reverse()
        conds = "; ".join(f"{p:#x} {mn}({lab}) after [{flag_setter(ins, order, p)}]" for p, mn, lab in chain) or "(条件なし)"
        rows.append((w, ins[w][1], n, conds))
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "ret584_paths.tsv"), "w") as f:
        f.write("write_VA\tsource\tpath_len\tbranch_conditions_on_shortest_path\n")
        for w, src, n, conds in rows:
            f.write(f"{w:#x}\t{src}\t{n}\t{conds}\n")
    print(f"writes_total={len(writes)} reachable_from_entry={len(rows)}")


if __name__ == "__main__":
    main()
