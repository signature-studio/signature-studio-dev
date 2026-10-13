"""leafabi.py — leaf 関数の xmm0 入出力 ABI 整備 (CAB-239, OTT leaf native spec 用)。

RetDec は double 戻り関数 (exp/log/tan 等) を「引数なし・戻り i64 (rax)」で lift する。
実際の機械語は xmm0 入力 / xmm0 戻りで, lifted IR は
  - 入力: 未 store alloca の load (B1 後 0) として読む (f2 pass が %xmmK_bits 引数化で修復)
  - 戻り: rax のゴミ値を返す (真の結果は xmm0)
の 2 点で壊れる。本 pass は機械語を正本に:

  ret  : 各 `ret i64 %v` で xmm0 の到達定義を bind し, i128 SSA が得られれば
         `ret i64 (trunc i128 %xmm0val to i64)` に差し替える (double bits を返す)。
  RX   : ret_xmm0 callee の call site を進行方向に走査し, xmm0 を最初に読む IR 行の
         「call 直前時点の xmm0 SSA (古い値 = RetDec の流し間違い)」を call 戻り値の
         zext に差し替える (exp 結果が caller に流れるようにする)。

f2 (入口 xmm 引数化) と組み合わせて leaf 関数を native 機械語と bit 突合可能にする。
"""
import os
import re

from .. import ir as IR
from ..mc import MFunc, leaf_ext
from ..regbind import Binder, result_type as regbind_result_type

CALL_RE = re.compile(r"^\s*(?:%[\w$.\-]+ = )?call (\S+) @(function_[0-9a-f]+)\((.*?)\)\s*(?:,.*)?$")


# LIFTLIB-5 (leaf cfg の leaf_ext 時のみ). ablation: LL_NO_RET_PHI=1 / LL_NO_RX_ALL=1
def _no_ret_phi():
    return not leaf_ext("RET_PHI")


def _all_readers():
    return leaf_ext("RX_ALL")


def _canon_xmm(it):
    from ..mc import _canon_reg
    return _canon_reg(it._ci, it.ops[0].reg)


def _canon_xmm_op(it, k):
    from ..mc import _canon_reg
    return _canon_reg(it._ci, it.ops[k].reg)


def _i128_args(s):
    """`... call iNN @__asm_x(i128 %a, i128 %b)` の i128 引数名 (順) を返す。"""
    m = re.search(r"call \S+ @__asm_[\w.]+\((.*)\)", s)
    if not m:
        return []
    return [a.split()[1] for a in IR.split_args(m.group(1)) if a.strip().startswith("i128 ")]


def _relocate(fn, bi, ln):
    """前方の挿入で ret 行の位置がずれた場合に備え, 同一 block 内で行を再探索する。"""
    b = fn.blocks[bi]
    return bi, b.lines.index(ln)


def _def_values(binder, d):
    """機械語 def d の xmm0 値を表す IR 命令 [(bi, ln, dst, ty)] (複製コピー全部)。
    i128 結果, または xmm0 戻り callee への call の i64/i32 戻り。"""
    out = []
    for (bi, li, ln) in binder.ix.instrs_at(d):
        dst = IR.instr_dst(ln)
        if not dst or not re.match(r"^\s*%[\w$.\-]+ = call ", IR.strip_tokens(ln)):
            continue                      # load / trunc 等の同一アドレス別命令は def の値ではない
        ty = regbind_result_type(ln)
        if ty == "i128" or (ty in ("i64", "i32") and binder.xmm0_ret_of_call(d)):
            out.append((bi, ln, dst, ty))
    return out


def _store_phi(mod, fn, used, tag_va, a_name, vals):
    """vals の各 IR 値の直後に alloca (i128) へ store する。alloca は entry 先頭 (0 初期化)。"""
    a = a_name
    k = 0
    while a in used:
        k += 1
        a = "%s%d" % (a_name, k)
    used.add(a)
    entry = fn.blocks[0]
    entry.lines.insert(0, "  store i128 0, ptr %s" % a)
    entry.lines.insert(0, "  %s = alloca i128" % a)
    t = mod.tag(tag_va)
    for (bi, ln, dst, ty) in vals:
        b = fn.blocks[bi]
        i = b.lines.index(ln)
        z = "%%lf_%x_pz%d" % (tag_va, len(used))
        used.add(z)
        if ty == "i128":
            b.lines.insert(i + 1, "  store i128 %s, ptr %s%s" % (dst, a, t))
        else:
            b.lines.insert(i + 1, "  store i128 %s, ptr %s%s" % (z, a, t))
            b.lines.insert(i + 1, "  %s = zext %s %s to i128%s" % (z, ty, dst, t))
    return a


def _call_phi(mod, fn, binder, va, used):
    """ret @va の xmm0 の到達 def (複数可) を全て同一 alloca (i128) に集める (reg2mem phi)。

    p1 は領域再構成で同一機械語アドレスの IR 命令を複製し, 単一 SSA が ret を支配しなくなる。
    各 def の全複製の直後で store し, ret 前で load する (最後に実行された def が勝つ)。
    ENTRY を含む / どれかの def に IR 値が無い場合は None (IR は変更しない)。"""
    r = binder.root_def("xmm0", va)
    if r[0] == "def":
        defs = {r[1]}
    elif r[0] == "multi":
        defs = set(r[1])
    else:
        return None
    if 0 in defs:
        return None
    vals = []
    for d in sorted(defs):
        v = _def_values(binder, d)
        if not v:
            return None
        vals.extend(v)
    if len(vals) < 2:
        return None
    return _store_phi(mod, fn, used, va, "%%lf_%x_phia" % va, vals)


def _ret_thread(mod, fn, mf, binder, log, stats):
    """define 内の各 ret で xmm0 を返すように差し替え。"""
    n = 0
    used = set()
    for b in fn.blocks:
        for ln in b.lines:
            d = IR.instr_dst(ln)
            if d:
                used.add(d)
    # 非支配値の弾き方 (p1._value_ok と同型): def のある block が ret の block を
    # 支配しないと clang の "does not dominate all uses" になる
    dom = binder.ix.dominators()

    def dominates_use(name, bi):
        if not (isinstance(name, str) and name.startswith("%")):
            return True
        d = binder.ix.defs.get(name)
        if d is None:
            return True
        return d[0] in dom[bi]

    def fresh(va, base):
        cand, k = "%%lf_%x_%s" % (va, base), 0
        while cand in used:                # 同一 ret VA を p1 が複製した block で衝突しうる
            k += 1
            cand = "%%lf_%x_%s%d" % (va, base, k)
        used.add(cand)
        return cand

    rets = [(bi, li) for bi, b in enumerate(fn.blocks)
            for li, ln in enumerate(b.lines) if re.match(r"^\s*ret i64 ", IR.strip_tokens(ln))]
    for bi, li in reversed(rets):          # 後方から (挿入で位置がずれないように)
        b = fn.blocks[bi]
        ln = b.lines[li]
        va = mod.addr_of(ln)
        if va is None:
            continue
        v = binder.bind("xmm0", va)
        if (v is None or v[1] == "i1" or not dominates_use(v[0], bi)) and not _no_ret_phi():
            # LIFTLIB-5: xmm0 の唯一の機械語 def が xmm0 戻り callee への call で, p1 の領域再構成が
            # その call を複製した (生存側 + 領域側の IR 命令が複数) とき, どの単一 SSA も ret を
            # 支配しない。各複製の直後で alloca に store し, ret 前で load する (reg2mem phi)。
            ph = _call_phi(mod, fn, binder, va, used)
            if ph is not None:
                bi, li = _relocate(fn, bi, ln)
                b = fn.blocks[bi]
                t = mod.tag(va)
                nn = fresh(va, "ph")
                t64 = fresh(va, "t")
                b.lines[li] = "  ret i64 %s%s" % (t64, t)
                b.lines.insert(li, "  %s = trunc i128 %s to i64%s" % (t64, nn, t))
                b.lines.insert(li, "  %s = load i128, ptr %s%s" % (nn, ph, t))
                n += 1
                stats["ret_phi"] = stats.get("ret_phi", 0) + 1
                continue
        if v is None or v[1] == "i1":
            stats["ret_unbound"] = stats.get("ret_unbound", 0) + 1
            continue
        if not dominates_use(v[0], bi):
            # LIFTLIB-4: 同一機械語アドレスに複数の領域コピーが在ると, bind が拾った値は
            # **別領域** の物でこの ret block からは非支配になり得る。候補を全件試して
            # この ret block を支配するものを選ぶ (従来は非支配で見送り = rax フラグを
            # 返す誤った ret になっていた)。
            pick = None
            for cand in binder.candidates_at("xmm0", va):
                if cand[1] == "i1":
                    continue
                if dominates_use(cand[0], bi):
                    pick = cand
                    break
            if pick is None:
                stats["ret_nodom"] = stats.get("ret_nodom", 0) + 1
                continue
            v = pick
            self_used = binder.ix.defs.get(v[0])
            if self_used is not None and self_used[0] == bi:
                pass                              # 同一 block 内定義 (正しい)

        if isinstance(v[0], str) and v[0].startswith("@@load:"):
            a = v[0][7:]
            t = mod.tag(va)
            nn = fresh(va, "ld")
            b.lines.insert(li, "  %s = load i128, ptr %s%s" % (nn, a, t))
            v = (nn, "i128")
            li += 1
        elif v[1] != "i128":
            # i64/i32 (xmm0 戻り callee の call 戻り / rax.0.reload 等) = xmm0 bits の下位 64bit
            t = mod.tag(va)
            nn = fresh(va, "ld")
            b.lines.insert(li, "  %s = zext %s %s to i128%s" % (nn, v[1], v[0], t))
            v = (nn, "i128")
            li += 1
        tag = mod.tag(va)
        t64 = fresh(va, "t")
        b.lines[li] = "  ret i64 %s%s" % (t64, tag)
        b.lines.insert(li, "  %s = trunc i128 %s to i64%s" % (t64, v[0], tag))
        n += 1
    stats["ret_threaded"] = stats.get("ret_threaded", 0) + n
    if n:
        log.append("leafabi ret %s: %d rets -> xmm0 bits" % (fn.name, n))
    return n


def _rx_thread(mod, fn, img, callee_set, log, stats):
    """call site 後の最初の xmm0 読みを call 戻り値へ差し替え (RX)。"""
    va0 = int(fn.name.split("_")[1], 16)
    rng = img.func_at(va0)
    if rng is None:
        return 0
    mf = MFunc(img, *rng)
    n = 0
    phis = {}
    fb_done = set()
    for bi, b in enumerate(fn.blocks):
        for li, ln in enumerate(list(b.lines)):
            s = IR.strip_tokens(ln)
            m = CALL_RE.match(s)
            if not m or m.group(2) not in callee_set or m.group(1) not in ("i64", "i32"):
                continue
            C = mod.addr_of(ln)
            if C is None:
                continue
            binder = Binder(mod, fn, mf)
            stale = binder.bind("xmm0", C)
            if stale is None or not str(stale[0]).startswith("%"):
                continue
            # 機械語を C の直後から進め, xmm0 を最初に読む命令を探す (xmm0 再定義で打切り)
            v = C + mf.insns[C].size if C in mf.insns else None
            readers = []
            while v is not None and v in mf.insns:
                it = mf.insns[v]
                if "xmm0" in it.reads:
                    readers.append(v)
                    if not _all_readers() or binder._is_region_dst(IR.instr_dst(ln) or ""):
                        break                   # 従来: 最初の読み手のみ (領域複製の call は 1 件)
                if "xmm0" in it.writes:
                    break
                if it.is_jmp or it.is_ret or it.is_call:
                    break                       # ブロック/呼出境界では追わない (保守的)
                v = it.next
            for reader in readers:
                if n and leaf_ext("REINDEX"):
                    # 前の挿入で行位置がずれるため, 読み手ごとに索引を作り直す (LEAF_EXT のみ)
                    binder = Binder(mod, fn, mf)
                n += _rx_one(mod, fn, binder, mf, ln, C, reader, stale, phis, fb_done, stats)
    stats["rx_threaded"] = stats.get("rx_threaded", 0) + n
    if n:
        log.append("leafabi rx %s: %d sites" % (fn.name, n))
    return n


def _rx_one(mod, fn, binder, mf, ln, C, reader, stale, phis, fb_done, stats):
    """call C (IR 行 ln) の戻りを, xmm0 の読み手 reader (機械語) の IR 行へ差し替える。差し替えた数 (0/1)。"""
    n = 0
    if True:
        lines = [x for x in binder.ix.instrs_at(reader) if stale[0] in IR.strip_tokens(x[2])]
        md0 = re.match(r"^\s*(%[\w$.\-]+) = call ", IR.strip_tokens(ln))
        if not lines and not _no_ret_phi() and mf.defs_before(reader, "xmm0") == {C} \
                and md0 and not binder._is_region_dst(md0.group(1)) and (C, reader) not in fb_done:
            fb_done.add((C, reader))
            # LIFTLIB-5: reader の xmm0 (第 1 引数) が RetDec の古い値 (call 前) を指しているが, bind(C) は
            # 多定義で別値に解決され照合できない。reader 行の第 1 i128 引数を stale として採る
            # (reader が xmm0 を dst/第1 operand に取る SSE 2 operand 形に限る)。
            rop = mf.insns[reader].ops
            if rop and rop[0].type == 1 and _canon_xmm(mf.insns[reader]) == "xmm0":
                for x in binder.ix.instrs_at(reader):
                    mm = re.search(r"call i128 @__asm_\w+\(i128 (%[\w$.\-]+)", IR.strip_tokens(x[2]))
                    if mm:
                        stale = (mm.group(1), "i128")
                        lines = [x]
                        break
        if not lines:
            return n
        bi2, li2, ln2 = lines[0]
        # 支配チェック: call を含む IR block が reader 行の block を支配する事
        cb = binder.ix.by_addr.get(C)
        if not cb or not binder.ix.dominates(cb[0][0], bi2):
            # LIFTLIB-5: reader が call を支配しない (p1 が call を複製した / 別 block) 時,
            # 機械語で xmm0 の唯一の到達 def が C なら, call 結果 (全複製) を alloca phi 経由で渡す
            if _no_ret_phi() or mf.defs_before(reader, "xmm0") != {C}:
                stats["rx_nodomin"] = stats.get("rx_nodomin", 0) + 1
                return n
            if C not in phis:
                vals = _def_values(binder, C)
                if not vals:
                    stats["rx_nodomin"] = stats.get("rx_nodomin", 0) + 1
                    return n
                used = {IR.instr_dst(x) for b_ in fn.blocks for x in b_.lines if IR.instr_dst(x)}
                phis[C] = _store_phi(mod, fn, used, C, "%%rx_%x_phia" % C, vals)
            rb = fn.blocks[bi2]
            ri = rb.lines.index(ln2)
            ldn = "%%rx_%x_pl" % reader
            k2 = 0
            while any(ldn in x for b_ in fn.blocks for x in b_.lines):
                k2 += 1
                ldn = "%%rx_%x_pl%d" % (reader, k2)
            tagr = mod.tag(reader)
            pat = re.compile("(?<![\\w$.\\-])" + re.escape(stale[0]) + "(?![\\w$.\\-])")
            rb.lines[ri] = pat.sub(ldn, ln2)
            rb.lines.insert(ri, "  %s = load i128, ptr %s%s" % (ldn, phis[C], tagr))
            n += 1
            stats["rx_phi"] = stats.get("rx_phi", 0) + 1
            return n
        tag = mod.tag(reader)
        # 呼出結果 (call の dst) を探す: 同一 call 行の dst
        md = re.match(r"^\s*(%[\w$.\-]+) = call ", IR.strip_tokens(ln))
        if not md:
            return n
        cret = md.group(1)
        z = "%%rx_%x_z" % reader
        zk = 0
        while any(z == IR.instr_dst(x_) for b_ in fn.blocks for x_ in b_.lines):
            zk += 1
            z = "%%rx_%x_z%d" % (reader, zk)
        newtok = "%s" % z
        # 同一 block の前回挿入で行位置がずれているため, 位置 (li2) でなく行の同一性で探し直す
        li2 = fn.blocks[bi2].lines.index(ln2)
        fn.blocks[bi2].lines.insert(li2, "  %s = zext i64 %s to i128%s" % (z, cret, tag))
        # ln2 内の stale トークンだけを差し替え (他の metadata (!range 等) はそのまま保持)
        pat = re.compile("(?<![\\w$.\\-])" + re.escape(stale[0]) + "(?![\\w$.\\-])")
        fn.blocks[bi2].lines[li2 + 1] = pat.sub(newtok, ln2)
        n += 1
    return n


def run(mod, img, ret_xmm0=(), log=None, stats=None, repair=True):
    """ret_xmm0: xmm0 戻り関数名のリスト (define)。ret 差し替え + 全 module の RX thread。"""
    log = log if log is not None else []
    stats = stats if stats is not None else {}
    if not repair:
        return stats
    callee_set = set(ret_xmm0)
    auto_off = bool(os.environ.get("LL_NO_XMM0_RET_AUTO"))
    # LIFTLIB-3: 命名非依存の xmm0 戻り推定。`ret_in_xmm0()` (全 ret で xmm0 が
    # 関数内定義 = 結果を xmm0 に書いて返す) の define を自動で callee_set に追加する。
    # tan → function_1801aa1a0 のように「間接的な xmm0 戻り callee」が cfg の
    # ret_xmm0 明示リストから漏れると tan の戻りが 0 になっていた (tan 1/40 の一因)。
    # rax は見ない (call 経路ではほぼ常に intra 定義になり誤って rax 戻りと誤認する)。
    for fn in list(mod.funcs()):
        nm = fn.name
        if nm in callee_set or not re.match(r"function_[0-9a-f]+$", nm):
            continue
        va = int(nm.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        if auto_off:                    # ablation (SUBAGENT_RULES 規則 41): 自動拡張を止める
            continue
        mf = MFunc(img, *rng)
        if mf.ret_in_xmm0():
            callee_set.add(nm)
            stats["ret_xmm0_auto"] = stats.get("ret_xmm0_auto", 0) + 1
    for nm in sorted(callee_set):
        fn = mod.func(nm)
        if fn is None:
            log.append("leafabi: %s not defined (skip ret)" % nm)
            continue
        va = int(nm.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        mf = MFunc(img, *rng)
        binder = Binder(mod, fn, mf)
        _ret_thread(mod, fn, mf, binder, log, stats)
    if callee_set:
        for fn in list(mod.funcs()):
            if re.match(r"function_[0-9a-f]+$", fn.name):
                _rx_thread(mod, fn, img, callee_set, log, stats)
    return stats
