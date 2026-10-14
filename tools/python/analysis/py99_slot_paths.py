#!/usr/bin/env python3
"""PY-99 (#3085・親 #2874): SLOT? の読みごとに、合流の先行辺ごとの store 集合を出し、別算法と突合する (実機不要)。

  python3 analysis/py99_slot_paths.py <work/py53/fn.txt> [--negctl drop-pred]

  <work/py53/fn.txt> は analysis/py53_dispatch.py の出力 (作業用ファイル)。
対象は analysis/py88_writes.py の既定 65 件のうち、直接式で SLOT[ を含む 49 件。
読み = py88 の式に現れる SLOT[rbp+X]?@j の葉 (読む命令 r と X の組)。

算法 B (後ろ向き): r から CFG の逆辺を BFS で遡り、[rbp+X] への dword/qword store で止める。
  線形に遡って最初に現れる合流 J (先行辺 2 本以上) と、J の先行辺 p ごとの S_p を出す。
算法 A (前向き): 同じ X について reaching-definitions の固定点計算 (gen = store・kill = 同 X の store)。
  読み r の IN(r) と B の到達 store 集合を 1 件ずつ比べ、mismatch 件数を出す。
--negctl drop-pred: 算法 B だけで、読みを VA 順に見て、合流 J の先行辺 p0 を 1 本外す。
  p0 は「S_p0 の store のうち、他の先行辺の S_q に無いものがある最初の (読み, p)」。
  他の辺と寄与が完全に重なる辺を外しても mismatch にならないため、その辺は選ばない。

store の式は py88 の Slicer.def_value で作る。閉じた式 = ⚠合流・SLOT? ほか未確定の葉 (ACC・IN・_in・clob・VCALL・CALL[・<・…・⚠addr-taken) を含まないもの。
exit: mismatch == 0 なら 0、それ以外は 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as p88  # noqa: E402

ENTRY = -1
SLOT_RE = re.compile(r"^(dword|qword) ptr \[rbp \+ (0x[0-9a-f]+)\]$")
SIZED_RE = re.compile(r"^(byte|word|dword|qword) ptr \[rbp \+ (0x[0-9a-f]+)\]$")
SIZES = {"byte": 1, "word": 2, "dword": 4, "qword": 8}
READ_RE = re.compile(r"^SLOT\[rbp\+(0x[0-9a-f]+)\]\?@")
UNCLOSED = ("⚠合流", "SLOT[", "ACC", "IN[", "_in", "clob@", "VCALL", "CALL[", "<", "…", "⚠addr-taken")


def closed(e):
    return not any(k in e for k in UNCLOSED)


class Cfg:
    def __init__(self, ins, order):
        self.ins = ins
        self.order = order
        self.idx = {a: i for i, a in enumerate(order)}
        self.pred = {a: [] for a in order}
        for i, a in enumerate(order):
            m, o = ins[a]
            nxt = order[i + 1] if i + 1 < len(order) else None
            if m == "ret":
                out = []
            elif m.startswith("j"):
                if not p88.TARGET_RE.fullmatch(o.strip()) or int(o, 16) not in self.idx:
                    raise SystemExit(f"unsupported branch at {a:#x}: {m} {o}")
                tgt = int(o, 16)
                out = [tgt] if m == "jmp" else [tgt, nxt]
            else:
                out = [nxt]
            for s in out:
                if s is not None and a not in self.pred[s]:
                    self.pred[s].append(a)

    def preds(self, a):
        p = list(self.pred[a])
        if a == self.order[0]:
            p.append(None)
        return p

    def store(self, a, x):
        m, o = self.ins[a]
        if m not in p88.STORE:
            return False
        ops = p88.parse_ops(o)
        mm = SLOT_RE.match(ops[0]) if ops else None
        return mm is not None and int(mm.group(2), 16) == x


def reach_before(cfg, c, x, cut=None):
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
                out.add(ENTRY)
            elif cfg.store(p, x):
                out.add(p)
            else:
                stack.append(p)
    return out


def reach_after(cfg, p, x, cut=None):
    if p is None:
        return {ENTRY}
    if cfg.store(p, x):
        return {p}
    return reach_before(cfg, p, x, cut)


def first_merge(cfg, r, x):
    cur, seen = r, set()
    while True:
        ps = cfg.preds(cur)
        if len(ps) >= 2:
            return cur
        if not ps or ps[0] is None or cfg.store(ps[0], x) or cur in seen:
            return None
        seen.add(cur)
        cur = ps[0]


def forward_in(cfg, x):
    pr = {a: cfg.preds(a) for a in cfg.order}
    inn = {a: set() for a in cfg.order}
    out = {a: set() for a in cfg.order}
    changed = True
    while changed:
        changed = False
        for a in cfg.order:
            new_in = set()
            for p in pr[a]:
                new_in |= {ENTRY} if p is None else out[p]
            new_out = {a} if cfg.store(a, x) else set(new_in)
            inn[a] = new_in
            if new_out != out[a]:
                out[a] = new_out
                changed = True
    return inn


class Rec(p88.Slicer):
    def __init__(self, ins, order):
        super().__init__(ins, order)
        self.reads = set()

    def mem_read(self, addr, size, pos, depth):
        v = super().mem_read(addr, size, pos, depth)
        mm = READ_RE.match(v)
        if mm:
            self.reads.add((self.order[pos], int(mm.group(1), 16)))
        return v


def fmt(s):
    return "{" + ", ".join("IN" if v == ENTRY else f"{v:#x}" for v in sorted(s)) + "}"


def main(argv):
    args = list(argv[1:])
    negctl = None
    if "--negctl" in args:
        k = args.index("--negctl")
        negctl = args[k + 1] if k + 1 < len(args) else ""
        del args[k:k + 2]
        if negctl != "drop-pred":
            sys.exit("usage: --negctl drop-pred")
    if len(args) != 1:
        sys.exit("usage: python3 analysis/py99_slot_paths.py <work/py53/fn.txt> [--negctl drop-pred]")
    path = args[0]
    ins, order = p88.load(path)
    cfg = Cfg(ins, order)
    shared = Rec(ins, order)

    writes, reads_by_write = [], {}
    for a in p88.default_targets(path):
        rec = Rec(ins, order)
        m, o = ins[a]
        val = rec.ev(p88.parse_ops(o)[1], cfg.idx[a], 0)
        cat = p88.category(val)
        if cat.startswith("直接式") and "SLOT?" in cat:
            writes.append(a)
            reads_by_write[a] = sorted(rec.reads)
    print(f"# 対象の書込み: {len(writes)} 件 (py88 既定 65 件のうち直接式で SLOT? のもの)")

    reads = {}
    for a in writes:
        for key in reads_by_write[a]:
            reads.setdefault(key, []).append(a)
    keys = sorted(reads)
    fwd = {}
    for r, x in keys:
        if x not in fwd:
            fwd[x] = forward_in(cfg, x)

    cut = None
    neg_note = ""
    if negctl:
        for r, x in keys:
            j = first_merge(cfg, r, x)
            if j is None:
                continue
            sets = {p: reach_after(cfg, p, x) for p in cfg.preds(j)}
            for p in cfg.preds(j):
                others = set().union(*[sets[q] for q in sets if q != p])
                if sets[p] - others:
                    cut = (p, j)
                    neg_note = f"read {r:#x} [rbp+{x:#x}]"
                    break
            if cut:
                break
        if not cut:
            sys.exit("negctl: 寄与を持つ先行辺が無い")
        p0 = "IN" if cut[0] is None else f"{cut[0]:#x}"
        print(f"# negctl drop-pred: 辺 {p0} -> {cut[1]:#x} を外す ({neg_note})")

    exprs, printed = {}, set()

    def expr_of(s):
        if s == ENTRY:
            return "IN"
        if s not in exprs:
            exprs[s] = shared.def_value(cfg.idx[s], 0)
        return exprs[s]

    mismatch = 0
    stat = {a: {"reads": 0, "merge": 0, "edges": 0, "closed": 1} for a in writes}
    n_merge = n_edges = n_entry = pairs_closed = pairs_open = 0
    edge_hist = {}
    body = []
    for r, x in keys:
        j = first_merge(cfg, r, x)
        reach = reach_before(cfg, r, x, cut)
        if reach != fwd[x][r]:
            mismatch += 1
            body.append(f"MISMATCH read {r:#x} [rbp+{x:#x}]: B={fmt(reach)} A={fmt(fwd[x][r])}")
        ok = bool(reach) and ENTRY not in reach and all(closed(expr_of(s)) for s in reach)
        wl = ", ".join(f"{w:#x}" for w in reads[(r, x)])
        body.append(f"read {r:#x} [rbp+{x:#x}] 書込み: {wl}")
        if j is None:
            body.append(f"  合流なし (線形に遡って最初の store または入口) reach={fmt(reach)}")
        else:
            n_merge += 1
            n_edges += len(cfg.preds(j))
            body.append(f"  J={j:#x} 先行辺={len(cfg.preds(j))}")
            for p in cfg.preds(j):
                sp = reach_after(cfg, p, x)
                ok_p = ENTRY not in sp and all(closed(expr_of(s)) for s in sp)
                hist = edge_hist.setdefault(len(sp), [0, 0])
                hist[0 if ok_p else 1] += 1
                tag = "  (negctl: 外した辺)" if cut == (p, j) else ""
                pl = "IN" if p is None else f"{p:#x}"
                body.append(f"    p={pl} S_p={fmt(sp)}{tag}")
                for s in sorted(sp):
                    if s == ENTRY:
                        continue
                    e = expr_of(s)
                    mark = "閉" if closed(e) else "未閉"
                    if s in printed:
                        body.append(f"      store {s:#x}: [{mark}] (上と同じ式)")
                    else:
                        printed.add(s)
                        body.append(f"      store {s:#x}: [{mark}] {e}")
        if ENTRY in reach:
            n_entry += 1
        for s in reach:
            if s != ENTRY and closed(expr_of(s)):
                pairs_closed += 1
            else:
                pairs_open += 1
        for a in reads[(r, x)]:
            st = stat[a]
            st["reads"] += 1
            if j is not None:
                st["merge"] += 1
                st["edges"] += len(cfg.preds(j))
            if not ok:
                st["closed"] = 0
    print("\n".join(body))

    print("# 書込み別 (reads = 読み数 / merge = 合流を持つ読み / edges = その合流の先行辺数 / closed = 1 なら全読みが閉)")
    for a in writes:
        st = stat[a]
        print(f"# {a:#x} reads={st['reads']} merge={st['merge']} edges={st['edges']} closed={st['closed']}")
    tot = {k: sum(stat[a][k] for a in writes) for k in ("reads", "merge", "edges", "closed")}
    print(f"# 集計: 書込み {len(writes)} 件・読み (書込み単位の和) {tot['reads']}・異なり {len(keys)}・"
          f"合流を持つ異なり読み {n_merge}・先行辺の和 (異なり読み) {n_edges}・IN に届く読み {n_entry}")
    print(f"# 集計: 閉じた (読み,store) 対 {pairs_closed}・未閉 {pairs_open}・閉じた書込み {tot['closed']}/{len(writes)}")
    for k in sorted(edge_hist):
        c, u = edge_hist[k]
        print(f"# 先行辺 (合流 J の p) の S_p: |S_p|={k} の辺 閉 {c} 件・未閉 {u} 件")
    print(f"# 算法 A (前向き固定点) と B (後ろ向き BFS) の比較: 対象 {len(keys)} 件・mismatch {mismatch} 件")

    xs = sorted({x for _, x in keys})
    taken = sum(1 for x in xs if x in shared.addr_taken)
    overlap = 0
    nonconst = 0
    for a in order:
        m, o = ins[a]
        ops = p88.parse_ops(o)
        if m not in p88.STORE or not ops or "[rbp" not in ops[0]:
            continue
        mm = SIZED_RE.match(ops[0])
        if mm is None:
            nonconst += 1
            continue
        off, sz = int(mm.group(2), 16), SIZES[mm.group(1)]
        if any(off != x and off < x + 4 and x < off + sz for x in xs):
            overlap += 1
    print(f"# 限界情報: 解析した X {len(xs)} 種のうち lea で取られるもの {taken}・"
          f"X と重なる別オフセットの frame store (byte/word/dword/qword 定数) {overlap} 件・"
          f"frame の非定数オフセット store {nonconst} 件")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
