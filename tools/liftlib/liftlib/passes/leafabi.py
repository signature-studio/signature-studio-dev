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
import re

from .. import ir as IR
from ..mc import MFunc
from ..regbind import Binder

CALL_RE = re.compile(r"^\s*(?:%[\w$.\-]+ = )?call (\S+) @(function_[0-9a-f]+)\((.*?)\)\s*(?:,.*)?$")


def _ret_thread(mod, fn, mf, binder, log, stats):
    """define 内の各 ret で xmm0 を返すように差し替え。"""
    n = 0
    rets = [(bi, li) for bi, b in enumerate(fn.blocks)
            for li, ln in enumerate(b.lines) if re.match(r"^\s*ret i64 ", IR.strip_tokens(ln))]
    for bi, li in reversed(rets):          # 後方から (挿入で位置がずれないように)
        b = fn.blocks[bi]
        ln = b.lines[li]
        va = mod.addr_of(ln)
        if va is None:
            continue
        v = binder.bind("xmm0", va)
        if v is None or v[1] != "i128":
            stats["ret_unbound"] = stats.get("ret_unbound", 0) + 1
            continue
        if isinstance(v[0], str) and v[0].startswith("@@load:"):
            a = v[0][7:]
            t = mod.tag(va)
            nn = "%%lf_%x_ld" % va
            b.lines.insert(li, "  %s = load i128, ptr %s%s" % (nn, a, t))
            v = (nn, "i128")
            li += 1
        tag = mod.tag(va)
        t64 = "%%lf_%x_t" % va
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
            reader = None
            while v is not None and v in mf.insns:
                it = mf.insns[v]
                if "xmm0" in it.reads:
                    reader = v
                    break
                if "xmm0" in it.writes:
                    break
                if it.is_jmp or it.is_ret or it.is_call:
                    break                       # ブロック/呼出境界では追わない (保守的)
                v = it.next
            if reader is None:
                continue
            lines = [x for x in binder.ix.instrs_at(reader) if stale[0] in IR.strip_tokens(x[2])]
            if not lines:
                continue
            bi2, li2, ln2 = lines[0]
            # 支配チェック: call を含む IR block が reader 行の block を支配する事
            cb = binder.ix.by_addr.get(C)
            if not cb or not binder.ix.dominates(cb[0][0], bi2):
                stats["rx_nodomin"] = stats.get("rx_nodomin", 0) + 1
                continue
            tag = mod.tag(reader)
            # 呼出結果 (call の dst) を探す: 同一 call 行の dst
            md = re.match(r"^\s*(%[\w$.\-]+) = call ", IR.strip_tokens(ln))
            if not md:
                continue
            cret = md.group(1)
            z = "%%rx_%x_z" % reader
            newtok = "%s" % z
            fn.blocks[bi2].lines.insert(li2, "  %s = zext i64 %s to i128%s" % (z, cret, tag))
            # ln2 内の stale トークンだけを差し替え (他の metadata (!range 等) はそのまま保持)
            pat = re.compile("(?<![\\w$.\\-])" + re.escape(stale[0]) + "(?![\\w$.\\-])")
            fn.blocks[bi2].lines[li2 + 1] = pat.sub(newtok, ln2)
            n += 1
    stats["rx_threaded"] = stats.get("rx_threaded", 0) + n
    if n:
        log.append("leafabi rx %s: %d sites" % (fn.name, n))
    return n


def run(mod, img, ret_xmm0=(), log=None, stats=None, repair=True):
    """ret_xmm0: xmm0 戻り関数名のリスト (define)。ret 差し替え + 全 module の RX thread。"""
    log = log if log is not None else []
    stats = stats if stats is not None else {}
    if not repair:
        return stats
    callee_set = set(ret_xmm0)
    for nm in ret_xmm0:
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
