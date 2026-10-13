"""inject.py — 検出器の検出力評価 (CAB-55 負の対照 / パターン注入)。

RetDec の欠陥を **健全な IR に人工的に注入**し, 検出器が拾うかを数える:
  F7 : `mov r64,[b+d]` に対応する `load i64` を削除し, 使用側を base 値に置換 (RetDec の deref 脱落を模擬)
  P1f: comis に続く jcc の `br i1` を `br label` (片側畳み込み) に置換 (フラグ undef → 分岐畳み込みを模擬)
  F2 : callee の `%xmmK_bits` 引数と call site の対応引数を除去 (xmm 引数落ちを模擬)
さらに **偽陽性** を, 修復済み IR に検出器を再走査して数える (期待 0)。
"""
import copy
import re

from . import ir as IR
from .mc import MFunc
from .passes import f7, f2, p1
from .regbind import Binder, FuncIndex


def _sites_f7(mod, fn, mf):
    """健全 IR 上の F7 注入候補: mov r64,[base+disp] に load i64 が注釈され, dest が後続のアドレス基準に使われる"""
    b = Binder(mod, fn, mf)
    out = []
    for X in mf.order:
        it = mf.insns[X]
        R = f7._is_ptr_load(it)
        if not R or it.mem["index"] or it.mem["base"] in (None, "rip", "rsp"):
            continue
        loads = [(bi, li, l) for (bi, li, l) in b.ix.instrs_at(X) if re.search(r"= load i64\b", IR.strip_tokens(l))]
        if len(loads) != 1:
            continue
        if not f7._uses_as_addr(mf, R, X):
            continue
        out.append((X, R, loads[0]))
    return out


def inject_f7(mod, fn, mf, X, R, load):
    """load を消し, その dst の使用を base 値へ置換 (注入)。成功時 True。"""
    b = Binder(mod, fn, mf)
    bi, li, ln = load
    dst = IR.instr_dst(ln)
    base = b.bind(mf.insns[X].mem["base"], X)
    if base is None or base[0].startswith("@@"):
        return False
    pat = re.compile(f7.token_re(dst))
    del fn.blocks[bi].lines[li]
    for blk in fn.blocks:
        blk.lines = [pat.sub(base[0], l) for l in blk.lines]
    return True


def eval_f7(mod, img, limit=None, max_total=None):
    """注入数 / 検出数 / 修復数 (サイトごとに関数を複製 → 注入 → scan で検出されるか → repair が走るか)"""
    inj = det = fixed = 0
    detail = []
    for fn in list(mod.funcs()):
        if max_total and inj >= max_total:
            break
        if not re.match(r"function_[0-9a-f]+$", fn.name):
            continue
        rng = img.func_at(int(fn.name.split("_")[1], 16))
        if not rng:
            continue
        mf = MFunc(img, *rng)
        sites = _sites_f7(mod, fn, mf)
        for (X, R, load) in sites[:limit]:
            fn2 = copy.deepcopy(fn)
            cand = [s for s in _sites_f7(mod, fn2, mf) if s[0] == X]
            if not cand or not inject_f7(mod, fn2, mf, X, R, cand[0][2]):
                continue
            inj += 1
            b = Binder(mod, fn2, mf)
            found = [c for c in f7.scan(mod, fn2, mf, b) if c[0] == X]
            if found:
                det += 1
                st, lg = {}, []
                f7.repair(mod, fn2, mf, Binder(mod, fn2, mf), X, found[0][1], found[0][2], st, lg)
                if st.get("repaired"):
                    fixed += 1
            elif len(detail) < 6:
                detail.append("miss %s@%x" % (fn.name, X))
    return dict(injected=inj, detected=det, repaired=fixed, misses=detail)


def eval_p1_fold(mod, img):
    """comis→jcc の `br i1` を `br label` に畳む注入 → analyze が folded/dropped と分類するか。"""
    inj = det = 0
    for fn in list(mod.funcs()):
        if not re.match(r"function_[0-9a-f]+$", fn.name):
            continue
        rng = img.func_at(int(fn.name.split("_")[1], 16))
        if not rng:
            continue
        mf = MFunc(img, *rng)
        recs = p1.analyze(mod, fn, mf, Binder(mod, fn, mf))
        for rec in recs:
            if rec["call"] is None:
                continue
            for c in rec["consumers"]:
                if c["kind"] != "jcc" or c["state"] != "branch":
                    continue
                fn2 = copy.deepcopy(fn)
                rec2 = [r for r in p1.analyze(mod, fn2, mf, Binder(mod, fn2, mf)) if r["A"] == rec["A"]][0]
                c2 = [x for x in rec2["consumers"] if x["J"] == c["J"]][0]
                bi, li, ln = c2["br"]
                mm = re.match(r"^(\s*)br i1 \S+, label %([\w$.\-]+), label %([\w$.\-]+)(.*)$", ln)
                if not mm:
                    continue
                fn2.blocks[bi].lines[li] = "%sbr label %%%s%s" % (mm.group(1), mm.group(2), mm.group(4))
                inj += 1
                rec3 = [r for r in p1.analyze(mod, fn2, mf, Binder(mod, fn2, mf)) if r["A"] == rec["A"]][0]
                c3 = [x for x in rec3["consumers"] if x["J"] == c["J"]][0]
                if c3["state"] in ("folded", "dropped"):
                    det += 1
    return dict(injected=inj, detected=det)


def eval_clean(mod, img):
    """健全 (修復済み) IR に検出器をかける偽陽性: F7 scan / P1 dropped / F2 未修復 callee"""
    fp_f7 = fp_p1 = 0
    for fn in mod.funcs():
        if not re.match(r"function_[0-9a-f]+$", fn.name):
            continue
        rng = img.func_at(int(fn.name.split("_")[1], 16))
        if not rng:
            continue
        mf = MFunc(img, *rng)
        b = Binder(mod, fn, mf)
        fp_f7 += len(f7.scan(mod, fn, mf, b))
        for rec in p1.analyze(mod, fn, mf, b):
            for c in rec["consumers"]:
                if c["state"] in ("dropped", "folded"):
                    fp_p1 += 1
    st, lg = {}, []
    f2.run(mod, img, lg, st, repair=False)
    pending = sum(1 for l in lg if l.startswith("F2 callee xmm live-in") and "function_" in l)
    return dict(f7_false_positive=fp_f7, p1_dropped_after_repair=fp_p1, f2_info=lg[:1])


def eval_f2(mod, img):
    """F2 注入: 修復済み IR から %xmmK_bits 引数を除去 (callee) し, call site の対応引数も落として検出力を測る。"""
    text = mod.dump()
    m2 = IR.Module.parse(text)
    injected = 0
    names = []
    for fn in m2.funcs():
        ps = fn.params()
        xp = [(ty, nm) for (ty, nm) in ps if re.match(r"%xmm\d+_bits$", nm)]
        if not xp:
            continue
        mm = IR.DEFINE.match(fn.sig)
        keep = [("%s %s" % (ty, nm)) for (ty, nm) in ps if not re.match(r"%xmm\d+_bits$", nm)]
        fn.sig = "define %s@%s(%s)%s{" % (mm.group(1), fn.name, ", ".join(keep), mm.group(4))
        for b in fn.blocks:
            for i, l in enumerate(b.lines):
                for (ty, nm) in xp:
                    if re.search(r"= (zext|add) \S+ %s\b" % re.escape(nm), l):
                        d = IR.instr_dst(l)
                        b.lines[i] = "  %s = xor i128 0, 0" % d
        names.append(fn.name)
        injected += 1
    # call site: `, iNN %f2_..._xK` を除去
    for fn in m2.funcs():
        for b in fn.blocks:
            for i, l in enumerate(b.lines):
                if "%f2_" in l:
                    b.lines[i] = re.sub(r",\s*i(?:32|64|128) %f2_[0-9a-f]+_x\d+", "", l)
    for i, it in enumerate(m2.items):
        if isinstance(it, str) and it.startswith("declare ") and any("@" + n + "(" in it for n in names):
            m2.items[i] = re.sub(r",\s*i(?:32|64|128)(?=[,)])", "", it)
    st, lg = {}, []
    f2.run(m2, img, lg, st, repair=False)
    return dict(injected=injected, detected=st.get("callees_pending", 0))


def eval_f2_xret(mod, img):
    """F2 xmm 戻り注入 (LIFTLIB #241): xmm 戻り搬送済み IR の各 `ret i64 %lf_*` を `ret i64 0` (xmm0 を落とした形) に
    1 件ずつ戻し, `f2.xmm_ret_scan` が当該 callee を検出するか数える。mod は修復済み IR (run_xmm_ret 後)。"""
    inj = det = 0
    for fn in list(mod.funcs()):
        if not re.match(r"function_[0-9a-f]+$", fn.name):
            continue
        base_bad = f2.xmm_ret_scan(mod, img, {fn.name}).get(fn.name, (0, 0))[1]
        for b in fn.blocks:
            for i, l in enumerate(b.lines):
                if not f2.XRET_OK_RE.match(IR.strip_tokens(l)):
                    continue
                old = b.lines[i]
                b.lines[i] = re.sub(r"ret i(64|32) %lf_[0-9a-f]+_t\d*", lambda m: "ret i%s 0" % m.group(1), old, count=1)
                inj += 1
                got = f2.xmm_ret_scan(mod, img, {fn.name}).get(fn.name, (0, 0))[1]
                if got == base_bad + 1:
                    det += 1
                b.lines[i] = old
    return dict(injected=inj, detected=det)
