"""f7.py — [F7] RetDec の「ポインタ deref (mov r64,[base+disp]) 脱落」の検出と修復。

症状 (OTT m9 [F7] / FA Gain F7' / KH Gain F7 で同型):
    mov rax, qword ptr [rdx]        ; rax = *(rdx)   ← IR に load が無く, rax の使用箇所が rdx (base) そのものを使う
    movss xmm1, dword ptr [r8+rax]
検出 (機械語正本): `mov r64, [mem]` で dest が後続命令のメモリ operand の base/index に使われるのに,
    その命令アドレス (insn.addr) に `load i64` が 1 つも注釈されていない。
修復: base 値 (IR 結合) から `inttoptr+load i64` を挿入し, dest を使う命令 (到達定義が当該 mov のみ) の
    IR 行内で base 値と解決するオペランドを load 結果に置換する。
"""
import re

from .. import ir as IR
from ..mc import MFunc
from ..regbind import Binder

GPR64 = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}


def _is_ptr_load(it):
    if it.mnem != "mov" or not it.mem or not it.mem["read"] or it.mem["size"] != 8:
        return None
    if len(it.ops) != 2 or it.ops[0].type != 1:
        return None
    from ..mc import _canon_reg
    r = _canon_reg(it._ci, it.ops[0].reg)
    return r if r in GPR64 else None


def _uses_as_addr(mf, R, X):
    """X の mov が定義した R をメモリ operand の base/index に使う命令 (到達定義 == {X})。"""
    out = []
    for va in mf.order:
        it = mf.insns[va]
        if va <= X or not it.mem:
            continue
        m = it.mem
        if R in (m["base"], m["index"]) and mf.defs_before(va, R) == {X}:
            out.append(va)
    return out


def _all_readers(mf, R, X):
    out = []
    for va in mf.order:
        it = mf.insns[va]
        if va > X and R in it.reads and mf.defs_before(va, R) == {X}:
            out.append(va)
    return out


def resolves_to(ix, tok, target, depth=0):
    if tok == target:
        return True
    if depth > 3 or not tok.startswith("%"):
        return False
    d = ix.defs.get(tok)
    if not d:
        return False
    ln = IR.strip_tokens(ix.fn.blocks[d[0]].lines[d[1]])
    m = re.match(r"^\s*%[\w$.\-]+ = load \S+, ptr (%[\w$.\-]+)", ln)
    if m and m.group(1) in ix.stores:
        sts = ix.stores[m.group(1)]
        return bool(sts) and all(resolves_to(ix, v[2], target, depth + 1) for v in sts)
    m = re.match(r"^\s*%[\w$.\-]+ = (?:zext|trunc|bitcast) \S+ (%[\w$.\-]+) to", ln)
    if m:
        return resolves_to(ix, m.group(1), target, depth + 1)
    return False


def token_re(tok):
    return r"(?<![\w$.%\-])" + re.escape(tok) + r"(?![\w$.\-])"


def scan(mod, fn, mf, binder):
    """脱落 load の候補リスト [(X, R, [users], had_ir)]。"""
    ix = binder.ix
    out = []
    for X in mf.order:
        it = mf.insns[X]
        R = _is_ptr_load(it)
        if not R:
            continue
        if any(re.search(r"= load i64\b", IR.strip_tokens(l)) for (_b, _l, l) in ix.instrs_at(X)):
            continue
        users = _uses_as_addr(mf, R, X)
        if not users:
            continue
        out.append((X, R, users, bool(ix.instrs_at(X))))
    return out


def repair(mod, fn, mf, binder, X, R, users, stats, log):
    ix = binder.ix
    it = mf.insns[X]
    m = it.mem
    if m["index"] or m["base"] in (None, "rip", "rsp"):
        log.append("F7 skip @%x: unsupported addressing (%s)" % (X, it.op_str))
        stats["unsupported_addr"] = stats.get("unsupported_addr", 0) + 1
        return False
    bb = binder.bind(m["base"], X)
    if bb is None:
        log.append("F7 skip @%x: base %s unbound" % (X, m["base"]))
        stats["unbound"] = stats.get("unbound", 0) + 1
        return False
    btok, bty = bb
    if btok.startswith("@@load:"):
        log.append("F7 skip @%x: base is merge alloca" % X)
        stats["unbound"] = stats.get("unbound", 0) + 1
        return False
    edits = []
    for Y in _all_readers(mf, R, X):
        for (bi, li, ln) in ix.instrs_at(Y):
            s = IR.strip_tokens(ln)
            for mt in re.finditer(r"(%[\w$.\-]+)", s):
                tok = mt.group(1)
                if tok == IR.instr_dst(s):
                    continue
                if resolves_to(ix, tok, btok):
                    edits.append((bi, li, tok, Y))
    seen, ed2 = set(), []
    for e in edits:
        k = (e[0], e[1], e[2])
        if k not in seen:
            seen.add(k)
            ed2.append(e)
    edits = ed2
    if not edits:
        log.append("F7 skip @%x: no user operand resolves to base %s" % (X, btok))
        stats["no_user"] = stats.get("no_user", 0) + 1
        return False
    # load 挿入位置: X 以降で最小の注釈アドレスを持つ命令 (同一機械語ブロック内) の直前
    blk_start = mf.block_of(X)
    nxt = None
    for a in sorted(ix.by_addr):
        if a > X and mf.block_of(a) == blk_start:
            nxt = a
            break
    if nxt is not None:
        pos_bi, pos_li = ix.by_addr[nxt][0]
    else:
        pos_bi, pos_li = min((e[0], e[1]) for e in edits)
    tag = mod.tag(X)
    base = "%%f7_%x" % X
    ins = []
    cur = btok
    if bty != "i64":
        ins.append("  %s_z = zext %s %s to i64%s" % (base, bty, btok, tag))
        cur = base + "_z"
    if m["disp"]:
        ins.append("  %s_a = add i64 %s, %d%s" % (base, cur, m["disp"], tag))
        cur = base + "_a"
    ins.append("  %s_p = inttoptr i64 %s to ptr%s" % (base, cur, tag))
    ins.append("  %s_v = load i64, ptr %s_p, align 8%s" % (base, base, tag))
    fn.blocks[pos_bi].lines[pos_li:pos_li] = ins
    shift = len(ins)
    for (bi, li, tok, Y) in edits:
        if bi == pos_bi and li >= pos_li:
            li += shift
        old = fn.blocks[bi].lines[li]
        fn.blocks[bi].lines[li] = re.sub(token_re(tok), base + "_v", old)
    stats["repaired"] = stats.get("repaired", 0) + 1
    log.append("F7 repaired @%x: mov %s,[%s%+d] -> load %s_v; %d operand(s) rewritten (%s)" %
               (X, R, m["base"], m["disp"], base, len(edits), ",".join(sorted(set(e[2] for e in edits)))))
    return True


def run_function(mod, fn, img, repair_on=True, log=None, stats=None, mf=None):
    stats = stats if stats is not None else {}
    log = log if log is not None else []
    if not re.match(r"function_[0-9a-f]+$", fn.name):
        return stats
    va = int(fn.name.split("_")[1], 16)
    rng = img.func_at(va)
    if rng is None:
        return stats
    mf = mf or MFunc(img, *rng)
    done = set()
    while True:
        binder = Binder(mod, fn, mf)
        cands = [c for c in scan(mod, fn, mf, binder) if c[0] not in done]
        if not cands:
            break
        X, R, users, had_ir = cands[0]
        done.add(X)
        stats["dropped_load"] = stats.get("dropped_load", 0) + 1
        if repair_on:
            repair(mod, fn, mf, binder, X, R, users, stats, log)
    return stats
