#!/usr/bin/env python3
"""PY-64 (#2788): 手計算の式 (REPORT_PY41_APPENDIX.md・PY-88 節の照合表) と機械スライス (py88_writes.py) を突合する (実機不要)。

  python3 analysis/py64_check_expr.py <work/py53/fn.txt> [--negctl {p2,one}]

- 手計算側 HAND は照合表の式を文字列で持つ (*(x) は逆参照・P は [rbp+0x5b8] へ書く前の基準ポインタ鎖)。
- 機械側は py88_writes.Slicer の出力 (ACC?⚠合流 は ACC と同一視し、件数だけ表示する)。
- 両者を同じ文法で式木にし、正規化してから比較する。+ と · は可換なので並べ替えて比較する。
- --negctl p2: 3 件の F 式の P を 2 段 (修正前の誤り) にして突合する。mismatch 3 が出るはず。
- --negctl one: 0x104c311 の P だけを 2 段にする。mismatch 1 が出るはず。
- mismatch が 1 件以上なら exit 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as w  # noqa: E402

P3 = {  # 3 段 (機械スライスと一致する正しい鎖)
    "0x104c2a6": "*(*(*(0x15e2eb8))+0x9e0)",
    "0x104c64f": "*(*(*(0x15e2eb8))+0xb28)",
    "0x104c919": "*(*(*(0x15e2eb8))+0x778)",
}
P2 = {  # 2 段 (修正前の誤り)
    "0x104c2a6": "*(*(0x15e2eb8)+0x9e0)",
    "0x104c64f": "*(*(0x15e2eb8)+0xb28)",
    "0x104c919": "*(*(0x15e2eb8)+0x778)",
}


P4 = {  # G8 (PY-359): 3 段 (機械スライスと一致する正しい鎖)
    "0x104c51a": "*(*(*(0x15e14a0))+0x808)",
}

# G4 (PY-4909): 0x104b305 は CALL[0x10469f0](ecx, edx, r8d) の戻り値。edx=0 (xor)・ecx=[rbp+0x5b8] の読み (0x104b2f2)・
# r8d=0x3e80。[rbp+0x5b8] は届く store が 0x1046d6b の 1 本だけで (py99 の CFG 到達定義)、その値は入口の edx (d_in)。
# 機械側は py99_slot_paths.ExpSlicer で展開した式を比べる (raw の py88 は CALL[...] のまま)。
G4 = "0 + rint(*(0x1046a20) · d_in · (0x3e80 − 0))"
EXPANDED = [(0x104b305, G4)]  # 展開版 (ExpSlicer) で突合する地点


def F(p):
    return f"*({p}+0x3b8) + rint(*(0x104ccd8) · ACC · (*({p}+0x3bc) − *({p}+0x3b8)))"


def hand_table(p):
    return [
        (0x104c311, F(p["0x104c2a6"])),
        (0x104c3f0, "*(*(0x15e36d8))"),
        (0x104c6ba, F(p["0x104c64f"])),
        (0x104c769, "*(*(0x15e2c50))"),
        (0x104c984, F(p["0x104c919"])),
        (0x104c9e6, "*(*(0x15e28c8))"),
        (0x104c51a, F(P4["0x104c51a"])),
        (0x104c56d, "*(*(0x15e3290))"),
    ]


TOKEN = re.compile(r"\s*(\*\(|0x[0-9a-fA-F]+|\d+|[A-Za-z_][A-Za-z0-9_]*|[()+\-*·])")


def tokenize(s):
    s = s.replace("−", "-")
    out, pos = [], 0
    s = s.rstrip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m:
            raise ValueError(f"未知の文字 {s[pos:pos + 12]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class Parser:
    def __init__(self, s):
        self.t = tokenize(s)
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, want=None):
        tok = self.peek()
        if tok is None or (want is not None and tok != want):
            raise ValueError(f"期待 {want!r} に対して {tok!r}")
        self.i += 1
        return tok

    def expr(self):
        terms = [self.term()]
        while self.peek() in ("+", "-"):
            op = self.take()
            t = self.term()
            terms.append(t if op == "+" else ("neg", t))
        return ("sum", terms)

    def term(self):
        fs = [self.factor()]
        while self.peek() in ("*", "·"):
            self.take()
            fs.append(self.factor())
        return ("prod", fs)

    def factor(self):
        t = self.take()
        if t == "*(":
            e = self.expr()
            self.take(")")
            return ("deref", e)
        if t == "(":
            e = self.expr()
            self.take(")")
            return e
        if t == "-":
            return ("neg", self.factor())
        if re.fullmatch(r"0x[0-9a-fA-F]+|\d+", t):
            return ("num", int(t, 0))
        if t == "f64" and self.peek() == "(":
            self.take("(")
            e = self.expr()
            self.take(")")
            return e
        if t == "rint" and self.peek() == "(":
            self.take("(")
            e = self.expr()
            self.take(")")
            return ("rint", e)
        if t in ("ACC", "d_in"):
            return (t,)
        raise ValueError(f"未知のトークン {t!r}")


def canon(t):
    k = t[0]
    if k in ("sum", "prod"):
        items = []
        for c in t[1]:
            c = canon(c)
            if c[0] == k:
                items.extend(c[1])
            else:
                items.append(c)
        if len(items) == 1:
            return items[0]
        return (k, sorted(items, key=repr))
    if k == "deref":
        return ("deref", canon(t[1]))
    if k == "neg":
        return ("neg", canon(t[1]))
    if k == "rint":
        return ("rint", canon(t[1]))
    return t


def parse_canon(s):
    p = Parser(s)
    e = p.expr()
    if p.peek() is not None:
        raise ValueError(f"末尾に余り {p.t[p.i:]!r}")
    return canon(e)


def machine_norm(s):
    s = re.sub(r"ACC\?⚠合流@0x[0-9a-f]+", "ACC", s)
    s = re.sub(r"(?<=[\w)\]])@0x[0-9a-f]+", "", s)
    s = re.sub(r"\bM(8|16|32|64)\[", "*(", s)
    s = s.replace("G[", "(").replace("[", "(").replace("]", ")")
    return s


def main():
    args = sys.argv[1:]
    negctl = None
    if "--negctl" in args:
        k = args.index("--negctl")
        negctl = args[k + 1]
        del args[k:k + 2]
    ins, order = w.load(args[0])
    s = w.Slicer(ins, order)
    p = dict(P3)
    if negctl == "p2":
        p = dict(P2)
    hand = hand_table(p)
    if negctl == "one":
        hand[0] = (0x104c311, F(P2["0x104c2a6"]))
    mism = 0
    acc_join = 0
    for va, h in hand:
        i = s.idx[va]
        m, o = ins[va]
        mach = s.ev(w.parse_ops(o)[1], i, 0)
        acc_join += mach.count("ACC?⚠合流")
        try:
            hc = parse_canon(h)
            mc = parse_canon(machine_norm(mach))
            ok = hc == mc
            detail = "" if ok else f"\n    hand={hc!r}\n    mach={mc!r}"
        except ValueError as e:
            ok = False
            detail = f"\n    parse error: {e}"
        mism += 0 if ok else 1
        print(f"{va:#x}: {'一致' if ok else '不一致'}{detail}")
    print(f"# n={len(hand)} mismatch={mism} ACC?⚠合流 (機械側・ACC と同一視) = {acc_join}", file=sys.stderr)
    emis = expanded_check(ins, order, s)
    sys.exit(1 if mism or emis else 0)


def expanded_check(ins, order, s):
    """PY-4909: py99_slot_paths の展開式 (SLOT・CALL[0x10469f0] を置換した式) と手計算式を突合する。"""
    import py99_slot_paths as p99
    mism = 0
    for va, h in EXPANDED:
        (_, mach, left), = p99.expand((ins, order), [va])
        try:
            ok = parse_canon(h) == parse_canon(machine_norm(mach)) and not left
            detail = "" if ok else f"\n    hand={h!r}\n    mach={mach!r} 未解決={left}"
        except ValueError as e:
            ok = False
            detail = f"\n    parse error: {e}\n    mach={mach!r} 未解決={left}"
        mism += 0 if ok else 1
        print(f"{va:#x} (展開版): {'一致' if ok else '不一致'}{detail}")
    print(f"# expanded n={len(EXPANDED)} mismatch={mism}", file=sys.stderr)
    return mism


if __name__ == "__main__":
    main()
