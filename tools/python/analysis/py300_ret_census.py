"""PY-300 (#4108): 0x1046a30 の戻り値 eax ([rbp+0x584]) の決まり方を制御フローの辺から集計する (実機不要)。

入力: pe_disasm.py 1046a30 4700 の出力 (fn.txt)。
線形 CFG の到達性だけを見る (データ依存の条件は評価しない)。
- EXIT_M1 (0x104cc72): 戻り値は初期値 -1 のまま ret する
- RET_N (0x104cc65): [rbp+0x5b8] (最終 n) を [rbp+0x584] へ複写して ret する
"""
import sys
from collections import deque

EXIT_M1 = 0x104CC72
RET_N = 0x104CC65
HEADS = [
    ("key 0", 0x10476E4), ("key 1", 0x1047934), ("key 2-3", 0x1047B93), ("key 4", 0x1047D75),
    ("key 5", 0x1047EDA), ("key 6", 0x1047FC6), ("key 7", 0x1048134), ("key 8", 0x104839C),
    ("key 9", 0x104882C), ("key a", 0x1048A15), ("key b", 0x1048B1B), ("key c", 0x1048C82),
    ("key d", 0x1048DCE), ("key e", 0x1048F81), ("key f", 0x1049110), ("key 0x10-0x14", 0x104933A),
    ("key 0x103-0x125 (0x10495e7)", 0x10495E7), ("neg 0x40000000", 0x104C2A6), ("neg 0x40000001", 0x104C4AF),
    ("neg 0x40000002", 0x104C64F), ("neg 0x40000005", 0x104C919), ("neg [0x70000000..)", 0x104AA87),
    ("neg others", 0x104CAAE), ("common tail 0x104a9ec", 0x104A9EC),
]


def parse(path):
    ins, order = {}, []
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split(" ", 1)
        if len(parts) < 2 or not parts[0].startswith("0x"):
            continue
        addr = int(parts[0], 16)
        mn, _, ops = parts[1].strip().partition(" ")
        ins[addr] = (mn, ops.strip())
        order.append(addr)
    return ins, order


def succ(ins, nxt, addr):
    mn, ops = ins[addr]
    n = nxt.get(addr)
    if mn == "ret":
        return []
    if mn == "jmp":
        return [int(ops, 16)] if ops.startswith("0x") else []
    if mn.startswith("j"):
        out = [int(ops, 16)] if ops.startswith("0x") else []
        if n is not None:
            out.append(n)
        return out
    return [n] if n is not None else []


def reach(ins, nxt, start):
    seen, q, hits = {start}, deque([start]), set()
    while q:
        a = q.popleft()
        if a in (EXIT_M1, RET_N):
            hits.add(a)
            continue
        if a not in ins:
            continue
        for b in succ(ins, nxt, a):
            if b is not None and b not in seen:
                seen.add(b)
                q.append(b)
    return hits


def main(path):
    ins, order = parse(path)
    nxt = {order[i]: order[i + 1] for i in range(len(order) - 1)}
    print(f"instructions={len(ins)}")
    print("edges into 0x104cc72 (-1 exit):")
    for a in sorted(ins):
        if EXIT_M1 in succ(ins, nxt, a) and a != EXIT_M1:
            print(f"  0x{a:x} {ins[a][0]} {ins[a][1]}")
    print("edges into 0x104cc65 (copy n):")
    for a in sorted(ins):
        if RET_N in succ(ins, nxt, a):
            print(f"  0x{a:x} {ins[a][0]} {ins[a][1]}")
    print("linear-CFG reachability from each head:")
    for name, h in HEADS:
        if h not in ins:
            print(f"  {name} 0x{h:x}: not in fn")
            continue
        hits = reach(ins, nxt, h)
        tags = [t for t, v in (("n(0x104cc65)", RET_N), ("-1(0x104cc72)", EXIT_M1)) if v in hits]
        print(f"  {name} 0x{h:x}: {' / '.join(tags) if tags else 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
