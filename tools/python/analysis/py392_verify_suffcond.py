#!/usr/bin/env python3
"""PY-392 (#4828): py392_ret584_suffcond.py が出した cube (十分条件の 1 本) を CFG 上で検証する。

  python3 analysis/py392_verify_suffcond.py <work/py53/fn.txt> <work/py392/suffcond.tsv>

各書込みの cube を読み、cube に現れない分岐は乱数で埋めた 3 本の割当で入口から歩く。
cube のリテラルで指定された分岐は必ずその辺を通る。書込みに届いた後、0x104cc65 まで
別の [rbp+0x5b8] 書込みを挟まずに届くことも同じ歩き方で確かめる。
出力: 件数 (cube 検証 ok/ng) のみ。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from py262_ret584_paths import ENTRY, WRITE_OP, edges, load  # noqa: E402

TARGET = 0x104CC65


def walk(ins, out, assign, start, stop_at, wset):
    v, seen = start, set()
    while True:
        if v in seen:
            return False
        seen.add(v)
        if v == stop_at:
            return True
        if v in wset and v != start:
            return False
        mn = ins[v][0]
        if mn.startswith("j") and mn != "jmp":
            take = assign.get(v)
            if take is None:
                take = False
            nxt = None
            for s, lab in out[v]:
                if (lab == "立ち") == take:
                    nxt = s
            if nxt is None:
                return False
            v = nxt
        elif out.get(v):
            v = out[v][0][0]
        else:
            return False


def main():
    ins, order = load(sys.argv[1])
    out = edges(ins, order)
    writes = [va for va in order if ins[va][0] == "mov" and ins[va][1].startswith(WRITE_OP)]
    wset = set(writes)
    ok = ng = 0
    with open(sys.argv[2]) as f:
        next(f)
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if p[6] != "True":
                continue
            w = int(p[0], 16)
            cube = {}
            if p[8] != "1":
                for lit in p[8].split(" & "):
                    neg = lit.endswith("!")
                    va = int(lit.rstrip("!"), 16)
                    cube[va] = not neg
            good = True
            for t in range(3):
                rnd = random.Random(w * 7 + t)
                a = {v: (rnd.random() < 0.5) for v in ins if ins[v][0].startswith("j") and ins[v][0] != "jmp"}
                if t == 0:
                    a = {v: False for v in a}
                a.update(cube)
                if not (walk(ins, out, a, ENTRY, w, set()) and walk(ins, out, a, w, TARGET, wset)):
                    good = False
            ok += good
            ng += not good
    print(f"cube_check ok={ok} ng={ng}")


if __name__ == "__main__":
    main()
