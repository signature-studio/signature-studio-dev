#!/usr/bin/env python3
"""PY-53 (#1911): ecx 分岐 (0x104742a〜0x104745f) を逆アセンブル結果から直接実行して照合する。

  python3 analysis/py53_ecx_check.py <work/py53/fn.txt> [--mutate]

py53_ecx_route.py の表 (手で導出) と、逆アセンブル命令の実行結果を境界値で比べる。
--mutate は 0x104742a の比較値を 1 つ壊し、MISMATCH が出ることを示すネガティブコントロール。
"""
import re
import sys

M = 0xFFFFFFFF
RANGE = (0x104742A, 0x104745F)
LEAVES = {0x104C4AF, 0x104C64F, 0x104C919, 0x104C2A6, 0x104AA87, 0x104CAAE, 0x1047497}


def load(path):
    rows = {}
    for ln in open(path):
        m = re.match(r"(0x[0-9a-f]+): (\S+)\s*(.*)", ln.strip())
        if m:
            rows[int(m.group(1), 16)] = (m.group(2), m.group(3))
    return rows


def signed(v):
    return v - 0x100000000 if v & 0x80000000 else v


def run(rows, ecx, mutate=False):
    order = sorted(rows)
    nxt = {a: order[i + 1] for i, a in enumerate(order[:-1])}
    eax = ecx & M
    flags = {}
    addr = RANGE[0]
    while addr not in LEAVES:
        mn, op = rows[addr]
        if mn == "cmp":
            imm = int(op.split(",")[1], 16) & M
            if mutate and addr == 0x104742A:
                imm = (imm + 1) & M
            flags = {"lhs": eax, "rhs": imm}
        elif mn == "sub":
            eax = (eax - int(op.split(",")[1], 16)) & M
            flags = {"lhs": eax, "rhs": 0}
        elif mn == "test":
            flags = {"lhs": eax, "rhs": 0}
        elif mn in ("jg", "jge", "jl", "je", "jne", "jb", "jae", "jmp"):
            l, r = flags["lhs"], flags["rhs"]
            if mn == "jmp":
                taken = True
            elif mn == "je":
                taken = l == r
            elif mn == "jne":
                taken = l != r
            elif mn == "jb":
                taken = l < r
            elif mn == "jae":
                taken = l >= r
            elif mn == "jg":
                taken = signed(l) > signed(r)
            elif mn == "jge":
                taken = signed(l) >= signed(r)
            else:
                taken = signed(l) < signed(r)
            if taken:
                addr = int(op, 16)
                continue
        addr = nxt[addr]
    return addr


def main():
    rows = load(sys.argv[1])
    mutate = "--mutate" in sys.argv
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from py53_ecx_route import CASES, route
    bad = 0
    for c in CASES:
        got = run(rows, c, mutate)
        exp = route(c)
        if got != exp:
            bad += 1
            print(f"MISMATCH ecx={c:#010x} asm={got:#x} table={exp:#x}")
    print(f"cases={len(CASES)} mismatch={bad} mutate={mutate}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
