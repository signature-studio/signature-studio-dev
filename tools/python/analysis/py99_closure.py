#!/usr/bin/env python3
"""PY-99 閉包 (#3104・親 #2874): SLOT? 49 件の書込みの値を、CFG 到達 store で再帰に閉じる (実機不要)。

  python3 analysis/py99_closure.py <work/py53/fn.txt> [--rint] [--callargs] [--negctl {drop-pred|drop-part}] [--md <out.md>]

--callargs: call 0x10469f0 の 7 件の引数 (ecx・edx・r8d) を、書込み式ではなく CALL 命令の引数式で閉じる (#4697)。

フレームの読み (r, X) は、r に CFG 上で届く store 集合 R(r, X) で置き換える。R の各 store s は、その値の式
(def_value) を同じ方法で閉じたものにする。R が 2 件以上なら経路別の場合分け {s1: E1 | s2: E2} になる。
  算法 B (後ろ向き BFS・既定): R = reach_before(r, X)。
  算法 A (前向き固定点・検算): R = forward_in(X)[r]。
書込みごとに A の閉包と B の閉包を比べ、文字列が違う件数を mismatch とする。
--negctl drop-pred: B だけで py99_merge_sets.py と同じ辺を 1 本外す (mismatch > 0 になるはず)。
--negctl drop-part: B だけで、読みの到達集合を一部だけ減らす辺を 1 本外す (--rint の 6 件用・寄与が重なる合流では drop-pred が選べないため)。
閉じた = 式に未確定の葉 (⚠合流・SLOT[・ACC・IN[・_in・clob@・VCALL・CALL[・<・…・⟪) を含まない。
exit: mismatch == 0 なら 0、それ以外は 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as p88  # noqa: E402
import py99_merge_sets as p99  # noqa: E402

LEAF_HEAD = ("SLOT[", "ACC", "IN[", "M8[rbp", "M16[rbp", "M32[rbp", "M64[rbp")
FR_RE = re.compile(r"FR\[(0x[0-9a-f]+)/(\d)\]@(0x[0-9a-f]+)")
RG_RE = re.compile(r"RG\[(\w+)\]@(0x[0-9a-f]+)")
UNCLOSED = ("⚠合流", "SLOT[", "ACC", "IN[", "_in", "clob@", "VCALL", "CALL[", "<", "…", "⚠addr-taken", "⟪")
LIMIT = 8000
SIZE_BYTES = {"byte": 1, "word": 2, "dword": 4, "qword": 8}


class Tag(p99.Rec):
    def __init__(self, ins, order):
        super().__init__(ins, order)
        self.lin_in = set()
        self.reg_in = set()
        self.frame_x = set()
        self.leaf_kind = {}
        self.width_bad = set()
        self.cfg = None
        self.store_sz = {}
        for a in order:
            m, o = ins[a]
            ops = p88.parse_ops(o)
            mm = re.match(r"^(byte|word|dword|qword) ptr \[rbp \+ (0x[0-9a-f]+)\]$", ops[0]) if m in p88.STORE and ops else None
            if mm:
                self.store_sz.setdefault(int(mm.group(2), 16), set()).add(SIZE_BYTES[mm.group(1)])

    def cfg_pred(self, a):
        return self.cfg.preds(a)

    def lin_def(self, fam, pos):
        i = pos - 1
        while i >= 0 and not defines(self.ins, self.order[i], fam):
            i -= 1
        return i

    def resolve(self, fam, pos, depth=0):
        lin = self.lin_def(fam, pos)
        if any(self.order[j] in self.targets for j in range(lin + 1, pos + 1)):
            return f"RG[{fam}]@{self.order[pos]:#x}"
        res = p88.Slicer.resolve(self, fam, pos, depth)
        if res.startswith(f"{fam}_in"):
            self.reg_in.add((fam, self.order[pos]))
        return res

    def reg_def_reaches(self, fam, pos_addr):
        """pos_addr の入口から CFG 上で fam を定義・clob する命令に届くか (届けば線形の _in は誤り)。"""
        stack, seen = list(self.cfg_pred(pos_addr)), set()
        while stack:
            p = stack.pop()
            if p is None:
                continue
            if p in seen:
                continue
            seen.add(p)
            m, o = self.ins[p]
            ops = p88.parse_ops(o)
            if m == "call" and fam in p88.CALLER_SAVED:
                return True
            if self.writes_fam(m, ops) == fam:
                return True
            stack.extend(self.cfg_pred(p))
        return False

    def mem_read(self, addr, size, pos, depth):
        v = p88.Slicer.mem_read(self, addr, size, pos, depth)
        if not addr.startswith("rbp"):
            return v
        off = addr[3:].replace(" ", "")
        try:
            x = int(off, 16) if off else 0
        except ValueError:
            return v
        sz = SIZE_BYTES[size]
        sizes = self.store_sz.get(x, set())
        if any(s in (1, 2) for s in sizes) or any(s < sz for s in sizes):
            self.width_bad.add((self.order[pos], x))
            return f"⟪幅{size}[rbp+{x:#x}]⟫"
        forced = sizes and sizes != {sz}
        if not forced and not v.startswith(LEAF_HEAD):
            return v
        if v.startswith("IN["):
            self.lin_in.add((self.order[pos], x))
        self.frame_x.add(x)
        if v.startswith("SLOT["):
            kind = "SLOT?"
        elif v.startswith("ACC?⚠合流"):
            kind = "ACC?⚠合流"
        elif v.startswith("ACC"):
            kind = "ACC"
        else:
            kind = "他"
        self.leaf_kind[(self.order[pos], x)] = kind
        return f"FR[{x:#x}/{sz}]@{self.order[pos]:#x}"


def defines(ins, a, fam):
    """命令 a が fam のレジスタ族を定義・clob するか (py88 の Slicer.resolve と同じ条件)。"""
    m, o = ins[a]
    ops = p88.parse_ops(o)
    if m == "call":
        return fam == "a" or fam in p88.CALLER_SAVED
    if m.startswith("cmov"):
        return bool(ops) and p88.FAM.get(ops[0]) == fam
    return bool(ops) and m in p88.WRITE_FIRST and p88.FAM.get(ops[0]) == fam


def reg_before(cfg, ins, c, fam, cut=None):
    out, seen, stack = set(), set(), [c]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for p in cfg.preds(n):
            if cut and (p, n) == cut:
                continue
            if p is None:
                out.add(p99.ENTRY)
            elif defines(ins, p, fam):
                out.add(p)
            else:
                stack.append(p)
    return out


def reg_forward(cfg, ins, fam):
    pr = {a: cfg.preds(a) for a in cfg.order}
    inn = {a: set() for a in cfg.order}
    out = {a: set() for a in cfg.order}
    changed = True
    while changed:
        changed = False
        for a in cfg.order:
            new_in = set()
            for p in pr[a]:
                new_in |= {p99.ENTRY} if p is None else out[p]
            new_out = {a} if defines(ins, a, fam) else set(new_in)
            inn[a] = new_in
            if new_out != out[a]:
                out[a] = new_out
                changed = True
    return inn


def unclosed_tokens(e):
    return [k for k in UNCLOSED if k in e]


def edges_direct(path):
    """cfg と別の経路 (テキストを直接読む) で辺集合を作る。"""
    rows = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        a, rest = ln.split(": ", 1)
        parts = rest.split(None, 1)
        rows.append((int(a, 16), parts[0], parts[1] if len(parts) > 1 else ""))
    nxt = {rows[i][0]: rows[i + 1][0] for i in range(len(rows) - 1)}
    E = set()
    for a, m, o in rows:
        if m == "ret":
            continue
        if m == "jmp":
            E.add((a, int(re.search(r"0x[0-9a-f]+", o).group(0), 16)))
        elif m.startswith("j"):
            E.add((a, int(re.search(r"0x[0-9a-f]+", o).group(0), 16)))
            if a in nxt:
                E.add((a, nxt[a]))
        elif a in nxt:
            E.add((a, nxt[a]))
    return E, rows[0][0], len(rows)


def check_cfg(path, cfg, order):
    E, entry, n = edges_direct(path)
    E_cfg = {(p, a) for a in order for p in cfg.pred[a] if p is not None}
    diff = len(E ^ E_cfg)
    seen, stack = {entry}, [entry]
    succ = {}
    for s, d in E:
        succ.setdefault(s, set()).add(d)
    while stack:
        n0 = stack.pop()
        for d in succ.get(n0, ()):
            if d not in seen:
                seen.add(d)
                stack.append(d)
    unreach = n - len(seen)
    return len(E), diff, unreach


def main(argv):
    args = list(argv[1:])
    negctl = None
    if "--negctl" in args:
        k = args.index("--negctl")
        negctl = args[k + 1] if k + 1 < len(args) else ""
        del args[k:k + 2]
        if negctl not in ("drop-pred", "drop-part"):
            sys.exit("usage: --negctl {drop-pred|drop-part}")
    want_rint = "--rint" in args
    if want_rint:
        args.remove("--rint")
    want_callargs = "--callargs" in args
    if want_callargs:
        args.remove("--callargs")
    md_out = None
    if "--md" in args:
        k = args.index("--md")
        md_out = args[k + 1] if k + 1 < len(args) else ""
        del args[k:k + 2]
        if not md_out or negctl:
            sys.exit("usage: --md <out.md> (--negctl と併用しない)")
    if len(args) != 1:
        sys.exit("usage: python3 analysis/py99_closure.py <work/py53/fn.txt> [--rint] [--negctl {drop-pred|drop-part}] [--md <out.md>]")
    path = args[0]
    ins, order = p88.load(path)
    cfg = p99.Cfg(ins, order)
    n_edges, diff, unreach = check_cfg(path, cfg, order)
    n_ind = sum(1 for a in order if ins[a][0] == "jmp" and not p88.TARGET_RE.fullmatch(ins[a][1].strip()))
    print(f"# CFG 検査: 辺 {n_edges}・テキスト直読みとの差 {diff}・入口から到達しない命令 {unreach}・間接 jmp {n_ind}")

    writes = []
    call_at = {}
    for a in p88.default_targets(path):
        r0 = p99.Rec(ins, order)
        m, o = ins[a]
        val = r0.ev(p88.parse_ops(o)[1], cfg.idx[a], 0)
        cat = p88.category(val)
        if want_rint:
            if cat.startswith("rint(") and ("SLOT?" in cat or "ACC?⚠合流" in cat):
                writes.append(a)
        elif want_callargs:
            if cat.startswith("CALL[未知の関数]") and val.startswith("CALL[0x10469f0]"):
                writes.append(a)
                call_at[a] = int(re.search(r"@(0x[0-9a-f]+)$", val).group(1), 16)
        elif cat.startswith("直接式") and "SLOT?" in cat:
            writes.append(a)
    label = "rint 6 件 (--rint)" if want_rint else "call 0x10469f0 の引数 (--callargs)" if want_callargs else "直接式 SLOT?"
    print(f"# 対象の書込み ({label}): {len(writes)} 件")

    T = Tag(ins, order)
    T.cfg = cfg
    raw = {}

    def store_expr(s):
        if s not in raw:
            raw[s] = T.def_value(cfg.idx[s], 0)
        return raw[s]

    cut = None
    if negctl:
        keys = set()
        for a in writes:
            r0 = p99.Rec(ins, order)
            r0.ev(p88.parse_ops(ins[a][1])[1], cfg.idx[a], 0)
            keys |= r0.reads
        if negctl == "drop-pred":
            for r, x in sorted(keys):
                j = p99.first_merge(cfg, r, x)
                if j is None:
                    continue
                sets = {p: p99.reach_after(cfg, p, x) for p in cfg.preds(j)}
                for p in cfg.preds(j):
                    others = set().union(*[sets[q] for q in sets if q != p])
                    if sets[p] - others:
                        cut = (p, j)
                        break
                if cut:
                    break
            if not cut:
                sys.exit("negctl: 寄与を持つ先行辺が無い")
        else:
            for r, x in sorted(keys):
                base = p99.reach_before(cfg, r, x)
                stack, seen, edges = [r], set(), set()
                while stack:
                    n = stack.pop()
                    if n in seen:
                        continue
                    seen.add(n)
                    for p in cfg.preds(n):
                        if p is None:
                            continue
                        edges.add((p, n))
                        if not cfg.store(p, x):
                            stack.append(p)
                for e in sorted(edges):
                    got = p99.reach_before(cfg, r, x, e)
                    if got and got != base:
                        cut = e
                        break
                if cut:
                    break
            if not cut:
                sys.exit("negctl: 到達集合を一部だけ減らす辺が無い")
        p0 = "IN" if cut[0] is None else f"{cut[0]:#x}"
        print(f"# negctl {negctl}: 辺 {p0} -> {cut[1]:#x} を外す")

    fwd = {}

    def store_size(s):
        return SIZE_BYTES[re.match(r"^(byte|word|dword|qword) ptr", p88.parse_ops(ins[s][1])[0]).group(1)]

    def run(mode, cut_edge):
        memo = {}
        multi = set()
        regfwd = {}

        def reach(r, x):
            if mode == "A":
                if x not in fwd:
                    fwd[x] = p99.forward_in(cfg, x)
                return fwd[x][r]
            return p99.reach_before(cfg, r, x, cut_edge)

        def reg_reach(r, fam):
            if mode == "A":
                if fam not in regfwd:
                    regfwd[fam] = reg_forward(cfg, ins, fam)
                return regfwd[fam][r]
            return reg_before(cfg, ins, r, fam, cut_edge)

        def close_leaf(x, sz, r, stack):
            R = reach(r, x)
            if not R:
                return "⟪到達なし⟫"
            if len(R) >= 2:
                multi.add((r, x))
            parts = []
            for s in sorted(R, key=lambda v: -1 if v == p99.ENTRY else v):
                if s == p99.ENTRY:
                    parts.append("⟪IN⟫")
                    continue
                e = close_store(s, stack)
                if store_size(s) > sz:
                    e = f"and({e}, {(1 << (8 * sz)) - 1:#x})"
                parts.append(f"{s:#x}: {e}")
            return "{" + " | ".join(parts) + "}"

        def close_reg(fam, r, stack):
            D = reg_reach(r, fam)
            if not D:
                return "⟪到達なし⟫"
            if len(D) == 1:
                return close_def(next(iter(D)), fam, stack)
            parts = []
            for d in sorted(D, key=lambda v: -1 if v == p99.ENTRY else v):
                if d == p99.ENTRY:
                    parts.append(f"{fam}_in")
                    continue
                parts.append(f"{d:#x}: {close_def(d, fam, stack)}")
            return "{" + " | ".join(parts) + "}"

        def close_def(d, fam, stack):
            if d == p99.ENTRY:
                return f"{fam}_in"
            key = ("R", d, fam)
            if key in memo:
                return memo[key]
            if key in stack:
                return "⟪循環⟫"
            m, o = ins[d]
            stack.append(key)
            if m == "call":
                out = expand(T.call_expr(cfg.idx[d], 0), stack) if fam == "a" else f"clob@{d:#x}"
            elif m.startswith("cmov"):
                out = f"CMOV@{d:#x}"
            else:
                out = expand(T.def_value(cfg.idx[d], 0), stack)
            stack.pop()
            if len(out) > LIMIT:
                out = "⟪長さ超過⟫"
            memo[key] = out
            return out

        def close_store(s, stack):
            if s in memo:
                return memo[s]
            if s in stack:
                return "⟪循環⟫"
            stack.append(s)
            out = expand(store_expr(s), stack)
            stack.pop()
            if len(out) > LIMIT:
                out = "⟪長さ超過⟫"
            memo[s] = out
            return out

        def expand(e, stack):
            e = FR_RE.sub(lambda m: leaf_of(m, stack), e)
            return RG_RE.sub(lambda m: close_reg(m.group(1), int(m.group(2), 16), stack), e)

        def leaf_of(m, stack):
            return close_leaf(int(m.group(1), 16), int(m.group(2), 10), int(m.group(3), 16), stack)

        res = {}
        for a in writes:
            m, o = ins[a]
            if want_callargs:
                val = re.sub(r"^CALL\[0x10469f0\]", "", T.call_expr(cfg.idx[call_at[a]], 0))
                val = re.sub(r"@0x[0-9a-f]+$", "", val)
            else:
                val = T.ev(p88.parse_ops(o)[1], cfg.idx[a], 0)
            res[a] = expand(val, [])
        return res, multi, memo

    resB, multiB, _ = run("B", cut)
    resA, _, _ = run("A", None)
    mismatch = 0
    for a in writes:
        if resB[a] != resA[a]:
            mismatch += 1
    closedB = [a for a in writes if not unclosed_tokens(resB[a])]
    closedA = [a for a in writes if not unclosed_tokens(resA[a])]
    reasons = {}
    for a in writes:
        for k in unclosed_tokens(resB[a]):
            reasons[k] = reasons.get(k, 0) + 1
    lin_in_reach = 0
    for r, x in sorted(T.lin_in):
        if p99.reach_before(cfg, r, x) - {p99.ENTRY}:
            lin_in_reach += 1
    reg_bad = sum(1 for f, a in sorted(T.reg_in) if T.reg_def_reaches(f, a))
    reg_only = [a for a in writes if set(unclosed_tokens(resB[a])) <= {"_in"}]
    print(f"# 入口のレジスタ値 (線形で定義なし) の読み {len(T.reg_in)} 件・CFG 上で定義が届く {reg_bad} 件")
    print(f"# 残る未確定が入口のレジスタ値 (_in) だけの書込み {len(reg_only)}/{len(writes)}")
    kinds = {}
    for k in T.leaf_kind.values():
        kinds[k] = kinds.get(k, 0) + 1
    print("# 閉じた frame 葉 (読み単位・異なり) の元の形: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    print(f"# 読みの幅が X の store の幅と違う frame 読み (未閉・⟪幅⟫) {len(T.width_bad)} 件")
    print(f"# 線形で IN とした読み {len(T.lin_in)} 件・CFG 上で store に届く {lin_in_reach} 件")
    print(f"# 多経路の読み (|R| >= 2) B {len(multiB)} 件")
    print(f"# 検算: 書込み {len(writes)} 件の閉包を A (前向き) と B (後ろ向き) で比較・mismatch {mismatch} 件")
    print(f"# 閉じた書込み (B) {len(closedB)}/{len(writes)}・(A) {len(closedA)}/{len(writes)}")
    print("# 未確定の葉 (B・書込み単位の件数): " + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    bw_hit = 0
    n_bw = 0
    for a in order:
        m, o = ins[a]
        ops = p88.parse_ops(o)
        if m not in p88.STORE or not ops:
            continue
        mm = re.match(r"^(byte|word) ptr \[rbp \+ (0x[0-9a-f]+)\]$", ops[0])
        if mm:
            n_bw += 1
            off, sz = int(mm.group(2), 16), (1 if mm.group(1) == "byte" else 2)
            if any(off < x + 8 and x < off + sz for x in T.frame_x):
                bw_hit += 1
    print(f"# 閉包が読んだ frame の X {len(T.frame_x)} 種・byte/word の frame store {n_bw} 件のうち X と重なる {bw_hit} 件 (store 判定の外)")

    if md_out:
        lines = [
            "自動生成: cd tools/python && python3 analysis/py99_closure.py work/py53/fn.txt --md analysis/py99_closure.md",
            "# PY-99 閉包 (#3104): SLOT? 書込み 49 件の値を CFG 到達 store で再帰に閉じた式 (算法 B)",
            "",
            "- `{s: E | s2: E2}` は読み点の CFG 到達 store の集合 (経路別)。`⟪IN⟫` は関数入口の値。",
            "- 閉: 式に SLOT[・ACC・⚠合流・CALL[・VCALL・clob@ などを含まない。残るのは入口のレジスタ値 `c_in`・`d_in`・`r8_in` だけ (CFG 上で定義が届かないことを確認済み)。",
            "- 列 `A=B`: 算法 A (前向き固定点) の閉包と算法 B の閉包が文字列として一致するか。",
            "",
            "| 書込み (VA) | 閉 | A=B | 式 |",
            "|---|---|---|---|",
        ]
        for a in writes:
            cl = "閉" if set(unclosed_tokens(resB[a])) <= {"_in"} else "未閉"
            same = "一致" if resA[a] == resB[a] else "不一致"
            cell = resB[a].replace("|", "\\|")
            lines.append(f"| {a:#x} | {cl} | {same} | `{cell}` |")
        with open(md_out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
