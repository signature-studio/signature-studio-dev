#!/usr/bin/env python3
"""PY-99 (#2874): [rbp+X] の読みごとに、CFG を後ろ向きに辿って届く store と格納値の式を列挙する (実機不要)。

  python3 analysis/py99_slot_paths.py <work/py53/fn.txt> [<VA> ...] [--negctl {fallthrough,expect}] [--lea-write]

- 対象は py88_writes の 65 書込みの式を評価する過程で現れる [rbp+X] の読み (Slicer.mem_read を記録する)。
- T: py88 の結果が SLOT[...]? または ACC?⚠ で始まる読み (印つき)。U: それ以外 (py88 の線形結果が一意)。
- U は py88 の線形遡りとの突合に使う。届く store が線形の直前 store 1 件で、式が py88 の式と一致すること。
- 辺: fall-through と jcc/jmp の target (関数内のみ)。store は py88 と同じ dword/qword ptr [rbp+X] への書込み。
- --negctl fallthrough: 分岐辺を全部落として列挙する (変わる読みの件数で検出力を見る)。
- --negctl expect: U の先頭 1 件の期待式を書き換える (不一致 1 で exit 1 になるはず)。
- --lea-write: lea [rbp+X] を間接書込み (may-write) とみなし、そこから直接の store を経ずに届く [rbp+X] の読みを数える (診断のみ・exit に影響しない)。
- expand((ins, order), vas): PY-4909 (#5800)。py88 の式の SLOT[rbp+X]? を届く store が 1 件の値で置換し、CALL[0x10469f0] を本体式に置換する (ExpSlicer)。未解決の印が残れば left に返す。
- 突合の不一致が 1 件以上なら exit 1。経路の列挙結果は stdout、集計は stderr に出す。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as w  # noqa: E402

SIZES = ("dword ptr [rbp + ", "qword ptr [rbp + ")
UNRESOLVED = ("SLOT[", "ACC", "IN[", "⚠", "_in", "clob@", "…", "OP:")
LEA = {"on": False}


def store_slot(ins, a):
    m, o = ins[a]
    ops = w.parse_ops(o)
    if LEA["on"] and m == "lea" and len(ops) == 2 and ops[1].startswith("[rbp + "):
        return int(ops[1].split("+ ")[1].rstrip("]"), 16)
    if m not in w.STORE or not ops or not ops[0].startswith(SIZES):
        return None
    return int(ops[0].split("+ ")[1].rstrip("]"), 16)


def store_value(sl, a):
    m, o = sl.ins[a]
    ops = w.parse_ops(o)
    if m in w.MOVLIKE and len(ops) == 2:
        return sl.ev(ops[1], sl.idx[a], 0)
    if m in w.ARITH and ops and ops[0].startswith(SIZES):
        return sl.rmw_expr(sl.idx[a], 0)
    return f"OP:{m} {o}"


def build(ins, order, branches=True):
    nxt = {a: (order[i + 1] if i + 1 < len(order) else None) for i, a in enumerate(order)}
    pred = {a: [] for a in order}
    brs = set()
    for a in order:
        m, o = ins[a]
        if m == "ret":
            continue
        if m.startswith("j"):
            tgt = int(o, 16) if w.TARGET_RE.fullmatch(o.strip()) else None
            if tgt is not None and tgt in ins and branches:
                pred[tgt].append(a)
                if m == "jmp" or tgt != nxt[a]:
                    brs.add((a, tgt))
            if m != "jmp" and nxt[a] is not None:
                pred[nxt[a]].append(a)
        elif nxt[a] is not None:
            pred[nxt[a]].append(a)
    return pred, brs


def lab_s(lab):
    return "直線" if lab is None else f"{lab:#x}"


def reach(sl, cfg, p, X, entry):
    pred, brs = cfg
    stores, inn, unreach, seen = {}, set(), 0, set()
    st = [(p, None, True)]
    while st:
        n, lab, first = st.pop()
        if not first:
            if (n, lab) in seen:
                continue
            seen.add((n, lab))
            if store_slot(sl.ins, n) == X:
                stores.setdefault(n, set()).add(lab_s(lab))
                continue
        if not pred[n]:
            if n == entry:
                inn.add(lab_s(lab))
            else:
                unreach += 1
            continue
        for m in pred[n]:
            st.append((m, n if lab is None and (m, n) in brs else lab, False))
    return stores, inn, unreach


def forward(sl, pred, X, entry):
    succ = {a: [] for a in sl.order}
    for n in sl.order:
        for m in pred[n]:
            succ[m].append(n)
    res = {}
    starts = [(s, s) for s in sl.order if store_slot(sl.ins, s) == X] + [(entry, "IN")]
    for s, tag in starts:
        seen, st = set(), (list(succ[s]) if tag != "IN" else [entry])
        while st:
            n = st.pop()
            if n in seen:
                continue
            seen.add(n)
            if store_slot(sl.ins, n) == X:
                continue
            st.extend(succ[n])
        for n in seen:
            res.setdefault(n, set()).add(tag)
    return res


def lin_store(sl, p, X):
    for j in range(sl.idx[p] - 1, -1, -1):
        if store_slot(sl.ins, sl.order[j]) == X:
            return sl.order[j]
    return None


def classify(sl, stores):
    if not stores:
        return "store 0 件"
    if len(stores) >= 2:
        return "分岐 (store 複数)"
    (s,) = stores
    v = store_value(sl, s)
    if v.startswith("OP:"):
        return "store 1 件 (kill: 非 mov)"
    if any(t in v for t in UNRESOLVED if t != "_in"):
        return "store 1 件・値に未確定印"
    if "_in" in v:
        return "store 1 件・値は入口レジスタに帰着"
    return "store 1 件で確定"


EXP_CALL = 0x10469F0  # edx + rint(2^-30 · ecx · (r8d − edx))。py99_call10469f0.py で PASS 済み
UNRESOLVED_EXP = ("SLOT[", "ACC?⚠", "clob@", "IN[", "⚠", "OP:", "CALL[", "VCALL", "…")


SIGN_DIV8 = [("test", "eax, eax"), ("jns", None), ("add", "eax, 7")]  # + sar eax, 3 (合流先)
SIGN_MOD8 = [("and", "eax, 0x80000007"), ("jns", None), ("sub", "eax, 1"), ("or", "eax, 0xfffffff8"),
             ("add", "eax, 1")]  # + 合流先の store (値 = mod8)


class ExpSlicer(w.Slicer):
    """py88 の式の SLOT[rbp+X]? と CALL[0x10469f0] を展開する。

    SLOT は届く store が 1 件・入口へ届かない・到達不能なし、の 3 条件を全部満たすときだけ、その store の値で置き換える
    (合流を越えても経路が 1 本に定まる場合のみ)。置換の後ろに `@<store の VA>` を付け、どの store から来たかを式に残す。
    届く store が複数 (分岐で値が割れる) なら置換せず、印をそのまま残す。
    符号付き /8 (SIGN_DIV8 → sar eax,3) と符号付き %8 (SIGN_MOD8) の分岐は、命令列が型に一致するときだけ
    div8(·)・mod8(·) の関数ノードに畳む (trunc 除算・剰余の全入力一致は py64_sign_branch_check.py で検証済み)。
    """

    def __init__(self, ins, order, cfg, entry):
        super().__init__(ins, order)
        self.cfg = cfg
        self.entry = entry
        self.active = set()

    def sign_match(self, start, tmpl, tgt):
        """order[start:start+len(tmpl)] が型に一致し、jns の飛び先が order[tgt] (= start+len(tmpl)) か。"""
        if start < 1 or tgt != start + len(tmpl) or tgt >= len(self.order):
            return False
        if any(self.order[j] in self.targets for j in range(start + 1, tgt)):
            return False
        for k, (m, o) in enumerate(tmpl):
            mi, oi = self.ins[self.order[start + k]]
            if mi != m:
                return False
            if o is None:
                if not (w.TARGET_RE.fullmatch(oi.strip()) and int(oi, 16) == self.order[tgt]):
                    return False
            elif oi != o:
                return False
        return True

    def def_value(self, i, depth):
        if self.ins[self.order[i]] == ("sar", "eax, 3") and self.sign_match(i - 3, SIGN_DIV8, i):
            return f"div8({self.resolve('a', i - 3, depth + 1)})@{self.order[i - 3]:#x}"
        return super().def_value(i, depth)

    def resolve(self, fam, pos, depth=0):
        if fam == "a" and self.sign_match(pos - 5, SIGN_MOD8, pos):
            return f"mod8({self.resolve('a', pos - 5, depth + 1)})@{self.order[pos - 5]:#x}"
        return super().resolve(fam, pos, depth)

    def mem_read(self, addr, size, pos, depth):
        r = super().mem_read(addr, size, pos, depth)
        mm = re.fullmatch(r"rbp \+(0x[0-9a-f]+)", addr)
        if not mm or not r.startswith(("SLOT[", "ACC?⚠")):
            return r
        X = int(mm.group(1), 16)
        if (pos, X) in self.active:
            return r
        stores, inn, unreach = reach(self, self.cfg, self.order[pos], X, self.entry)
        if inn or unreach or len(stores) != 1:
            return r
        (s,) = stores
        self.active.add((pos, X))
        try:
            v = store_value(self, s)
        finally:
            self.active.discard((pos, X))
        if v.startswith("OP:"):
            return r
        return f"({v})@{s:#x}"

    def call_expr(self, i, depth):
        a = self.order[i]
        m, o = self.ins[a]
        if w.TARGET_RE.fullmatch(o.strip()) and int(o, 16) == EXP_CALL:
            d = self.resolve("d", i, depth + 1)
            c = self.resolve("c", i, depth + 1)
            r8 = self.resolve("r8", i, depth + 1)
            return f"({d} + rint(M64[G[0x1046a20]] · {c} · ({r8} − {d})))@{a:#x}"
        return super().call_expr(i, depth)


def expand(path_or_lines, vas):
    """VA ごとに展開後の式と未解決印の一覧を返す。戻り値: [(va, expr, [未解決印])]。"""
    ins, order = path_or_lines
    cfg = build(ins, order, True)
    sl = ExpSlicer(ins, order, cfg, order[0])
    out = []
    for va in vas:
        m, o = ins[va]
        expr = sl.ev(w.parse_ops(o)[1], sl.idx[va], 0)
        left = sorted({t for t in UNRESOLVED_EXP if t in expr})
        out.append((va, expr, left))
    return out


def main():
    args = sys.argv[1:]
    lea_chk = "--lea-write" in args
    args = [a for a in args if a != "--lea-write"]
    neg = None
    if "--negctl" in args:
        k = args.index("--negctl")
        neg = args[k + 1]
        del args[k:k + 2]
    path = args[0]
    ins, order = w.load(path)
    sl = w.Slicer(ins, order)
    entry = order[0]
    targets = [int(x, 16) for x in args[1:]] or w.default_targets(path)

    rec = {}
    orig = sl.mem_read

    def rec_read(addr, size, pos, depth):
        r = orig(addr, size, pos, depth)
        mm = re.fullmatch(r"rbp \+(0x[0-9a-f]+)", addr)
        if mm:
            rec.setdefault((pos, int(mm.group(1), 16)), r)
        return r

    sl.mem_read = rec_read
    for a in targets:
        sl.ev(w.parse_ops(ins[a][1])[1], sl.idx[a], 0)

    full = build(ins, order, True)
    ft = build(ins, order, False)
    cfg = ft if neg == "fallthrough" else full

    indirect = sum(1 for a in order if ins[a][0].startswith("j") and not w.TARGET_RE.fullmatch(ins[a][1].strip()))
    print(f"# fn={len(order)} branch_edges={len(full[1])} indirect_jmp={indirect} targets={len(targets)} reads={len(rec)}")

    ordered = sorted(rec.items(), key=lambda kv: (order[kv[0][0]], kv[0][1]))
    T = [(order[pos], X, r) for (pos, X), r in ordered if r.startswith(("SLOT[", "ACC?⚠"))]
    U = [(order[pos], X, r) for (pos, X), r in ordered if not r.startswith(("SLOT[", "ACC?⚠"))]

    cls_cnt, in_cnt, at_cnt, unr_cnt, dist = {}, 0, 0, 0, {}
    for p, X, r in T:
        stores, inn, unreach = reach(sl, cfg, p, X, entry)
        c = classify(sl, stores)
        cls_cnt[c] = cls_cnt.get(c, 0) + 1
        dist[len(stores)] = dist.get(len(stores), 0) + 1
        in_cnt += bool(inn)
        at_cnt += X in sl.addr_taken
        unr_cnt += bool(unreach)
        print(f"T {p:#x} [rbp+{X:#x}] {c} stores={len(stores)} IN={'yes' if inn else 'no'} "
              f"addr-taken={'yes' if X in sl.addr_taken else 'no'} unreach={unreach}  py88: {r[:120]}")
        for s in sorted(stores):
            print(f"    store {s:#x} via {sorted(stores[s])}: {store_value(sl, s)}")

    match = mismatch = u_addr = 0
    first_u = True
    for p, X, r in U:
        stores, inn, unreach = reach(sl, cfg, p, X, entry)
        j = lin_store(sl, p, X)
        exp = r
        if neg == "expect" and first_u and j is not None:
            exp = r + " ⟂negctl"
        first_u = False
        if j is None:
            ok = not stores and bool(inn) and not unreach
            u_addr += "addr-taken" in r
        else:
            ok = (set(stores) == {j} and not inn and not unreach and store_value(sl, j) == exp)
        if ok:
            match += 1
        else:
            mismatch += 1
            print(f"MISMATCH U {p:#x} [rbp+{X:#x}] py88={exp[:160]} linear={j and hex(j)} "
                  f"reach={ {hex(k): sorted(v) for k, v in stores.items()} } IN={bool(inn)} unreach={unreach}")
    print(f"# U check: n={len(U)} match={match} mismatch={mismatch} (addr-taken={u_addr})")

    fcache, fmis = {}, 0
    for p, X, _ in T + U:
        if X not in fcache:
            fcache[X] = forward(sl, cfg[0], X, entry)
        fw = fcache[X].get(p, set())
        bw = reach(sl, cfg, p, X, entry)
        if {t for t in fw if t != "IN"} != set(bw[0]) or ("IN" in fw) != bool(bw[1]):
            fmis += 1
            print(f"MISMATCH FWD {p:#x} [rbp+{X:#x}] fwd={sorted(fw)} bwd={sorted(bw[0])} IN={bool(bw[1])}")
    print(f"# forward cross-check: n={len(T) + len(U)} mismatch={fmis}")

    diff = 0
    for p, X, _ in T + U:
        a = reach(sl, full, p, X, entry)
        b = reach(sl, ft, p, X, entry)
        if (set(a[0]), bool(a[1]), a[2]) != (set(b[0]), bool(b[1]), b[2]):
            diff += 1
    print(f"# fallthrough-only CFG: 変わった読み {diff} / {len(T) + len(U)}", file=sys.stderr)

    print(f"# T n={len(T)} (addr-taken={at_cnt}, IN reached={in_cnt}, unreach={unr_cnt}); store count dist={dict(sorted(dist.items()))}",
          file=sys.stderr)
    for k, v in sorted(cls_cnt.items(), key=lambda kv: -kv[1]):
        print(f"# {v:3d}  {k}", file=sys.stderr)
    print(f"# U n={len(U)} match={match} mismatch={mismatch}; forward n={len(T) + len(U)} mismatch={fmis}",
          file=sys.stderr)

    if lea_chk:
        LEA["on"] = True
        lv = [a for a in order if ins[a][0] == "lea" and store_slot(ins, a) == 0x5B8]
        fw = forward(sl, cfg[0], 0x5B8, entry)
        acc = [p for p, X, _ in T + U if X == 0x5B8]
        hit = [p for p in acc if fw.get(p, set()) & set(lv)]
        nodes = sum(1 for t in fw.values() if t & set(lv))
        LEA["on"] = False
        print(f"# lea-write: lea {[hex(a) for a in lv]} から直接 store を経ずに届く節点 {nodes}、"
              f"[rbp+0x5b8] の読み {len(hit)} / {len(acc)} (hit={[hex(p) for p in hit]})", file=sys.stderr)
    return 0 if mismatch == 0 and fmis == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
