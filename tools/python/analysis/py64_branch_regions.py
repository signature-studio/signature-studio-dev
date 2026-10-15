#!/usr/bin/env python3
"""PY-64 (#2033): 0x1046a30 の分岐先 6 件の固有部分 (共通後半 0x104caae の手前) を集計する (実機不要)。

  python3 analysis/py64_branch_regions.py <work/py53/fn.txt>

入力は analysis/py53_dispatch.py が出す fn.txt (capstone 逆アセンブル)。
各分岐先から到達できる命令のうち、共通後半 0x104caae と早期 exit 0x104cc72 の手前までを対象にし、
[rbp+0x5b8] へ書く命令 (直前の命令つき) と、0x104cc72 (戻り値 -1) へ飛ぶ分岐元を出す。
"""
import sys

TARGETS = [0x1047497, 0x104AA87, 0x104CAAE, 0x104C2A6, 0x104C64F, 0x104C919]
TAIL = 0x104CAAE
EXIT = 0x104CC72


def load(path):
    ins, order = {}, []
    for ln in open(path):
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        addr, rest = ln.split(": ", 1)
        parts = rest.split(None, 1)
        a = int(addr, 16)
        ins[a] = (parts[0], parts[1] if len(parts) > 1 else "")
        order.append(a)
    nxt = {a: order[i + 1] if i + 1 < len(order) else None for i, a in enumerate(order)}
    return ins, nxt


def succ(ins, nxt, a):
    m, o = ins[a]
    if m == "ret":
        return []
    if m == "jmp":
        return [int(o, 16)]
    if m.startswith("j"):
        return [int(o, 16), nxt[a]]
    return [nxt[a]]


def region(ins, nxt, start):
    seen, st = set(), [start]
    while st:
        a = st.pop()
        if a is None or a in seen:
            continue
        if a in (TAIL, EXIT) and a != start:
            continue
        seen.add(a)
        st.extend(succ(ins, nxt, a))
    return sorted(seen)


def main():
    ins, nxt = load(sys.argv[1])
    for t in TARGETS:
        r = region(ins, nxt, t)
        rs = set(r)
        exits = [f"{a:#x}" for a in r if ins[a][0].startswith("j") and ins[a][1] == f"{EXIT:#x}"]
        print(f"== {t:#x}: instr={len(r)} exit_-1_jumps={exits}")
        for a in r:
            m, o = ins[a]
            if m == "mov" and o.startswith("dword ptr [rbp + 0x5b8],"):
                prev = [p for p in r if nxt.get(p) == a]
                pv = ins[prev[0]] if prev else ("", "")
                print(f"  W5b8 {a:#x}: {m} {o}  <- {hex(prev[0]) if prev else '-'}: {pv[0]} {pv[1]}")


if __name__ == "__main__":
    main()
