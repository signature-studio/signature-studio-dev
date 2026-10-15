#!/usr/bin/env python3
"""PY-262 (#3860): 戻り値 `[rbp+0x584]` の書込み元 (0x104cc65 に届く `[rbp+0x5b8]` の書込み) を後ろ向きに列挙する。

  python3 analysis/py65_ret584_reach.py <work/py53/fn.txt> <target VA>

入力は py53_dispatch.py の fn.txt。target (既定 0x104cc65 = `mov eax, [rbp+0x5b8]`) から
predecessor (直前の命令・jcc の飛び先) を辿り、`mov dword ptr [rbp+0x5b8], *` に当たった所で止める。
経路条件は分けない (path-insensitive)。出力は VA と命令を 1 件 1 行、末尾に件数。
"""
import re
import sys
from collections import defaultdict

ADDR_RE = re.compile(r"(0x[0-9a-f]+): (\S+)\s*(.*)$")
WRITE_OP = "dword ptr [rbp + 0x5b8], "


def load(path):
    ins = {}
    order = []
    for ln in open(path):
        m = ADDR_RE.match(ln.rstrip("\n"))
        if m:
            va = int(m.group(1), 16)
            ins[va] = (m.group(2), m.group(3).strip())
            order.append(va)
    return ins, order


def preds(ins, order):
    idx = {va: i for i, va in enumerate(order)}
    p = defaultdict(list)
    for i, va in enumerate(order):
        mn, op = ins[va]
        if mn.startswith("j"):
            m = re.match(r"(0x[0-9a-f]+)", op)
            if m and int(m.group(1), 16) in idx:
                p[int(m.group(1), 16)].append(va)
        if mn not in ("jmp", "ret") and i + 1 < len(order):
            p[order[i + 1]].append(va)
    return p


def main():
    ins, order = load(sys.argv[1])
    target = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x104CC65
    p = preds(ins, order)
    seen = set()
    found = []
    stack = [target]
    while stack:
        v = stack.pop()
        if v in seen:
            continue
        seen.add(v)
        mn, op = ins.get(v, ("", ""))
        if v != target and mn == "mov" and op.startswith(WRITE_OP):
            found.append(v)
            continue
        stack.extend(p.get(v, []))
    for v in sorted(found):
        mn, op = ins[v]
        print(f"{hex(v)}  {mn} {op}")
    print("count", len(found))
    if "--gap" in sys.argv:
        direct = [v for v in order if ins[v][0] == "mov" and ins[v][1].startswith(WRITE_OP)]
        print("direct writes", len(direct))
        for v in direct:
            if v in found:
                continue
            k = order.index(v)
            nxt_write = next(w for w in order[k + 1:] if ins[w][0] == "mov" and ins[w][1].startswith(WRITE_OP))
            between = order[k:order.index(nxt_write)]
            straight = not any(ins[x][0].startswith("j") or ins[x][0] == "ret" for x in between)
            print(f"gap {hex(v)}  not reaching target; killed by {hex(nxt_write)} straight-line={straight}")


if __name__ == "__main__":
    main()
