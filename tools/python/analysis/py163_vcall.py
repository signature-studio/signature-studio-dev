#!/usr/bin/env python3
"""PY-163 (#3135): PY-88 の VCALL 3 件 (呼出し 0x104a8a0・0x104a95c・0x104a9c4) の引数と戻り値の式を、CFG 上の到達定義で求める (実機不要)。

  python3 analysis/py163_vcall.py <work/py53/fn.txt> [--check] [--negctl r9c]

- フレーム変数 (dword/qword の [rbp+X]) の読みを、py88_writes の線形の直前 store ではなく、
  py160_reach.build の基本ブロック CFG 上の到達定義で置き換える (分岐と back edge を越える)。
  ACC ([rbp+0x5b8]) も同じ CFG 上で読む (py88 の ACC?⚠合流 印は線形の近似。0x104a861・0x104a984 の rint の入力は CFG 上は入口の edx のみ)。
- 引数 lea で渡したアドレスへの書込み (call の out 引数) を定義とする。
  0x1331340 は rdx の [rbp+0x118] へ必ず書く (kill)。0xc61250 は条件付きの書込み (gen・PY-160 の事実)。
- --check: 手計算 (HAND) と機械側の式の集合を突合する (3 呼出し × 4 項 = 12 項)。
  手計算は呼出し直前の機械語を読んで手で書いた式。別算法として、命令単位の BFS (bfs_defs) で
  12 読みの到達定義集合をブロック単位の固定点と突合する (bfs-check n=12 mismatch=0)。
- --negctl r9c: 0x104a9c4 の r9d の手計算を 0x20 にする。mismatch 1 が出るはず (exit 1)。
- mismatch が 1 件以上なら exit 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as w  # noqa: E402
import py160_reach as r  # noqa: E402

SITES = [  # (呼出し VA, 書込み VA, ecx の読み (O2), edx の読み, r8d の読み, r9d の読み)
    (0x104A8A0, 0x104A8A3, 0x104A87C, 0x104A883, 0x104A889, 0x104A890),
    (0x104A95C, 0x104A95F, 0x104A938, 0x104A93F, 0x104A945, 0x104A94C),
    (0x104A9C4, 0x104A9C7, 0x104A99F, 0x104A9A6, 0x104A9AC, 0x104A9B3),
]
OUT_KILL = {0x104A792: 0x118}  # 0x1331340: rdx の [rbp+0x118] へ必ず書く
OUT_GEN = {0x104A92B: 0x5B8}  # 0xc61250: 条件付き (0xc6129a) で [r8] の [rbp+0x5b8] へ書く
OBJ = 0x410
EDX = 0x570
ACC = 0x5B8
R9 = 0x5C0
CFG_SLOTS = (0x118, 0x548, 0x564, 0x570, 0x580, 0x5B0, 0x5C0, 0x410)
SIZES = ("dword", "qword")
RMW = {"and": "&", "or": "|", "add": "+", "sub": "-", "xor": "^"}
WRITE_MNEM = r.WRITE_MNEM | {"and"}
IMM_RE = re.compile(r"-?(0x[0-9a-f]+|\d+)")


def tok(off):
    return f"[rbp + {off:#x}]"


def is_write(m, o, off):
    ops = w.parse_ops(o)
    return m in WRITE_MNEM and bool(ops) and any(ops[0] == f"{sz} ptr {tok(off)}" for sz in SIZES + ("byte",))


def pre_states(ins, order, off):
    """命令ごとの実行前の到達定義集合。定義は命令アドレス・初期値は "IN"。"""
    blocks, succ = r.build(ins, order)
    n = len(blocks)
    pred = {k: [] for k in range(n)}
    for k, ss in succ.items():
        for s_ in ss:
            pred[s_].append(k)

    def step(state, a):
        m, o = ins[a]
        if OUT_KILL.get(a) == off:
            return frozenset({a})
        if OUT_GEN.get(a) == off:
            return state | {a}
        if is_write(m, o, off):
            return frozenset({a})
        return state

    IN = {k: frozenset() for k in range(n)}
    OUT = {k: frozenset() for k in range(n)}
    IN[0] = frozenset({"IN"})
    changed = True
    while changed:
        changed = False
        for k in range(n):
            new_in = IN[0] if k == 0 else (frozenset().union(*[OUT[p] for p in pred[k]]) if pred[k] else frozenset())
            st = new_in
            for a in blocks[k]:
                st = step(st, a)
            if new_in != IN[k] or st != OUT[k]:
                IN[k], OUT[k] = new_in, st
                changed = True
    pre = {}
    for k in range(n):
        st = IN[k]
        for a in blocks[k]:
            pre[a] = st
            st = step(st, a)
    return pre


class CfgSlicer(w.Slicer):
    """py88_writes.Slicer の frame 読みを CFG 到達定義で置き換えたもの。"""

    def __init__(self, ins, order, pre):
        super().__init__(ins, order)
        self.pre = pre

    def mem_read(self, addr, size, pos, depth):
        mm = re.fullmatch(r"rbp\+(0x[0-9a-f]+)", addr.replace(" ", ""))
        if mm and int(mm.group(1), 16) in self.pre and size in SIZES:
            return self.cfg_value(int(mm.group(1), 16), self.order[pos], depth + 1)
        return super().mem_read(addr, size, pos, depth)

    def cfg_value(self, off, a, depth):
        """命令 a の実行前に [rbp+off] が持つ値 (到達定義の集合)。"""
        if depth > 40:
            return "…"
        st = self.pre[off][a]
        if st == {"IN"}:
            return f"IN[rbp+{off:#x}]"
        parts = sorted({self.def_val(off, d, depth + 1) for d in st})
        return parts[0] if len(parts) == 1 else "{" + " ∪ ".join(parts) + "}"

    def def_val(self, off, d, depth):
        """定義 d (命令アドレス・"IN") が書く値。"""
        if d == "IN":
            return f"IN[rbp+{off:#x}]"
        if d in OUT_KILL or d in OUT_GEN:
            return f"OUT({'0x1331340' if d in OUT_KILL else '0xc61250'})@{d:#x}"
        m, o = self.ins[d]
        ops = w.parse_ops(o)
        i = self.idx[d]
        if m in RMW and len(ops) == 2 and "[rbp" in ops[0]:
            return f"({self.cfg_value(off, d, depth + 1)} {RMW[m]} {ops[1]})"
        if m == "mov" and len(ops) == 2 and "[rbp" in ops[0]:
            src = ops[1]
            if src in w.FAM:
                return self.resolve(w.FAM[src], i, depth + 1)
            if IMM_RE.fullmatch(src):
                return src
            return self.ev(src, i, depth + 1)
        return f"<{m} {o}>@{d:#x}"

    def terms(self, off, a):
        """命令 a で [rbp+off] を読んだときの、定義ごとの値の集合 (ACC の定義集合は表示用)。"""
        return {self.def_val(off, d, 0) for d in self.pre[off][a]}


HAND = {  # 手計算 (呼出し直前の機械語を読んだ式)。edx は [rbp+0x564]・[rbp+0x5b0] の定義を手で畳んだ式
    "ecx=O2": {"VCALL[qword ptr [rax + 0x20]]@0x104a7a8"},
    "edx": {"(and(c_in, 0xffff) - 0x8000)", "((and(c_in, 0xffff) + 0x70000000) - 0x70008000)"},
    "r8d A": {"d_in", "rint((f64(d_in) * *(0x104cd00)))"},
    "r8d B": {"VCALL[qword ptr [rax + 0x30]]@0x104a8a0", "OUT(0xc61250)@0x104a92b", "d_in"},
    "r8d C": {"d_in", "rint((f64(d_in) * *(0x104cd00)))"},
    "r9d A": {"0x20"},
    "r9d B": {"2"},
    "r9d C": {"r8_in"},
}


def bfs_defs(ins, order, off, read):
    """別算法の検算: 命令単位の BFS で、read に届く定義 (命令アドレス・"IN") の集合を求める。
    kill は命令単位 (OUT_GEN の call は kill しない)。pre_states (ブロック単位の固定点) と突合する。"""
    idx = {a: i for i, a in enumerate(order)}
    writers = {a for a in order if is_write(*ins[a], off) or OUT_KILL.get(a) == off or OUT_GEN.get(a) == off}
    kills = {a for a in writers if OUT_GEN.get(a) != off}

    def succs(a):
        m, o = ins[a]
        i = idx[a]
        if m == "ret":
            return []
        if m.startswith("j"):
            out = [int(o, 16)] if int(o, 16) in idx else []
            return out + ([order[i + 1]] if m != "jmp" and i + 1 < len(order) else [])
        return [order[i + 1]] if i + 1 < len(order) else []

    def reach_from(starts, blockers):
        seen, stack, hit = set(), list(starts), False
        while stack:
            a = stack.pop()
            if a in seen:
                continue
            seen.add(a)
            if a == read:
                hit = True
            if a in blockers:
                continue
            stack.extend(succs(a))
        return hit

    res = {d for d in writers if reach_from(succs(d), kills)}
    if reach_from([order[0]], kills):
        res.add("IN")
    return res


def norm(t):
    return re.sub(r"ACC\?⚠合流@0x[0-9a-f]+", "ACC", t).replace("M64[G[0x104cd00]]", "*(0x104cd00)")


def main():
    args = sys.argv[1:]
    do_check = "--check" in args
    negctl = None
    if "--negctl" in args:
        k = args.index("--negctl")
        if k + 1 >= len(args) or args[k + 1] != "r9c":
            print("usage: --negctl r9c (値なし・未知の値はエラー)", file=sys.stderr)
            sys.exit(2)
        negctl = args[k + 1]
        del args[k:k + 2]
    ins, order = w.load(args[0])
    pre = {off: pre_states(ins, order, off) for off in CFG_SLOTS + (ACC,)}
    s = CfgSlicer(ins, order, pre)
    rows = []
    for call, wr, ld_obj, ld_edx, ld_r8, ld_r9 in SITES:
        tag = {0x104A8A0: "A", 0x104A95C: "B", 0x104A9C4: "C"}[call]
        print(f"## VCALL {call:#x} (書込み {wr:#x})")
        for name, ld, off in (("ecx=O2", ld_obj, OBJ), ("edx", ld_edx, EDX), ("r8d", ld_r8, ACC), ("r9d", ld_r9, R9)):
            if name == "r9d" and ld in (0x104A890, 0x104A94C):
                val = {ins[ld][1].split(", ")[1]}
                print(f"  r9d @{ld:#x}: {ins[ld][1]} (定数)")
            else:
                st = pre[off][ld]
                print(f"  {name} @{ld:#x} ({ins[ld][0]} {ins[ld][1]}) <- {{{', '.join(sorted(fmt(d) for d in st))}}}")
                val = {norm(t) for t in s.terms(off, ld)}
                for t in sorted(val):
                    print(f"      式: {t}")
            rows.append((f"{name} {tag}", val))
    print("## O1 の連鎖 (0x104a797 の [rbp+0x118]・0x104a784 の [rbp+0x548])")
    for ld, off in ((0x104A797, 0x118), (0x104A784, 0x548)):
        print(f"  [rbp+{off:#x}] @{ld:#x} <- {{{', '.join(sorted(fmt(d) for d in pre[off][ld]))}}}")
        for t in sorted({norm(x) for x in s.terms(off, ld)}):
            print(f"      式: {t}")
    if do_check:
        mism = 0
        nb = 0
        for off, a in ((OBJ, 0x104A87C), (OBJ, 0x104A938), (OBJ, 0x104A99F), (EDX, 0x104A883), (EDX, 0x104A93F), (EDX, 0x104A9A6),
                       (ACC, 0x104A861), (ACC, 0x104A889), (ACC, 0x104A945), (ACC, 0x104A984), (ACC, 0x104A9AC), (R9, 0x104A9B3)):
            nb += 1
            if bfs_defs(ins, order, off, a) != set(pre[off][a]):
                mism += 1
                print(f"bfs 不一致 [rbp+{off:#x}] @{a:#x}: bfs={sorted(map(fmt, bfs_defs(ins, order, off, a)))} cfg={sorted(map(fmt, pre[off][a]))}")
        print(f"# bfs-check n={nb} mismatch={mism}", file=sys.stderr)
        for key, val in rows:
            hand = HAND[key.split()[0] if key.split()[0] in ("ecx=O2", "edx") else key]
            if negctl == "r9c" and key == "r9d C":
                hand = {"0x20"}
            ok = hand == val
            mism += 0 if ok else 1
            print(f"{key:9s} {'一致' if ok else '不一致'}  hand={sorted(hand)}  mach={sorted(val)}")
        print(f"# n={len(rows)} mismatch={mism}", file=sys.stderr)
        sys.exit(1 if mism else 0)


def fmt(d):
    return "IN(関数入口)" if d == "IN" else f"{d:#x}"


if __name__ == "__main__":
    main()
