"""f2.py — [F2] RetDec の「xmm 引数落ち」の検出と修復。

MS x64 ABI の浮動小数引数は xmm0..3 (引数スロット位置 = xmm 番号)。RetDec は GPR 引数 (rcx/rdx/r8/r9) だけを
`%argN` として define に載せ, xmm 引数は
  - callee: 「未初期化値 (raw: 未 store alloca の load / B1 後: `xor i128 0, 0`)」として読まれ,
  - caller: call の直前に xmmK を作った命令の結果が捨てられる
状態になる (OTT m6/m8 [F2] SVF xmm1, FA Gain F2' meter)。
機械語を正本に
  - callee の入口 live-in xmm0..3 を到達定義から算出 (読取命令の mnemonic で f32/f64/v128 を判定)
  - callee の define に `%xmmK_bits` 引数 (i32/i64/i128) を追加し, undef 値を置換
  - 全 call site で xmmK を bind して引数に追加
を行う。
"""
import re

from .. import ir as IR
from ..mc import MFunc, XMM_ARGS
from ..regbind import Binder, FuncIndex

SS_RE = re.compile(r"(ss|ps2pd|cvtss|ss2)$")


def classify_kind(mf, k):
    """xmm_k の入口 live-in 読取命令から kind を決める。"""
    reg = "xmm%d" % k
    kinds = set()
    readers = []
    for va in mf.order:
        it = mf.insns[va]
        if reg in it.reads and 0 in mf.defs_before(va, reg):
            readers.append(va)
            m = it.mnem.lstrip("v")
            if m.endswith("ss") or m in ("cvtss2sd", "comiss", "ucomiss") or m.endswith("ss2si"):
                kinds.add("f32")
            elif m.endswith("sd") or m in ("cvtsd2ss", "comisd", "ucomisd") or m.endswith("sd2si"):
                kinds.add("f64")
            elif m in ("movq", "movd", "movmskps", "movmskpd"):
                # GPR への bits 抽出は double/float bits として受ける (wasm ABI は i64/i32)
                kinds.add("f64" if m in ("movq", "movmskpd") else "f32")
            else:
                kinds.add("v128")
    if not readers:
        return None, []
    kind = "f32" if "f32" in kinds else ("f64" if "f64" in kinds else "v128")
    if kind == "v128":
        # v128 のままでは wasm ABI が 2 個に lower され呼出側と合わないため,
        # f64 bits (下位 64 bit) で受ける。高 lane を使う callee は native spec が乖離として
        # 検出する (OTT leaf ではスカラー引数が実情) — CAB-239
        kind = "f64"
    return kind, readers


def xmm_params(mf):
    """{k: (kind, readers)} for xmm0..3 live-in."""
    out = {}
    live = mf.live_in()
    for k in range(4):
        reg = "xmm%d" % k
        if reg not in live:
            continue
        kind, readers = classify_kind(mf, k)
        if kind:
            out[k] = (kind, readers)
    return out


PTY = {"f32": "i32", "f64": "i64", "v128": "i128"}
UNDEF_RE = re.compile(r"^\s*(%[\w$.\-]+) = xor i128 0, 0\s*(?:,.*)?$")


def find_undef_for(mod, fn, ix, readers):
    """readers (機械語アドレス) を users に持つ undef 定義行 (xor i128 0,0) を探す: (bi, li, name)"""
    rs = set(readers)
    for bi, b in enumerate(fn.blocks):
        for li, ln in enumerate(b.lines):
            m = UNDEF_RE.match(IR.strip_tokens(ln))
            if not m:
                continue
            name = m.group(1)
            pat = re.compile(r"(?<![\w$.%\-])" + re.escape(name) + r"(?![\w$.\-])")
            for b2 in fn.blocks:
                for l2 in b2.lines:
                    if l2 is ln:
                        continue
                    if pat.search(IR.strip_tokens(l2)):
                        a = mod.addr_of(l2)
                        if a in rs:
                            return bi, li, name
    return None


def run(mod, img, log=None, stats=None, repair=True, only=None, phase="both", ix_map=None):
    """phase: "callee" (define/declare への %xmmK_bits 追加) / "callsite" (call site 引数接続)
    / "both" (従来通り)。LIFTLIB-2 では pipeline が callee 相を p1 より前に流す
    (p1 の領域が入口 xmm 値を bind できるようにするため)。callsite 相は p1 後
    (構造変更後の IR に対して今日と同じ条件で bind する)。

    ix_map: {関数名: p1 実行前の FuncIndex} — callsite 相の bind を p1 が生成した
    領域コピー (同じ機械語 VA のタグ付き行) ではなく元 IR の値で解決するために使う。
    領域コピーは別経路の値なので, 生存側 call site の bind がそれを拾うと
    支配違反 (他経路の SSA を参照) になる。"""
    stats = stats if stats is not None else {}
    log = log if log is not None else []
    funcs = {f.name: f for f in mod.funcs()}
    # ---- callee 解析: モジュール内 define + declare 先
    names = set(funcs)
    for it in mod.items:
        if isinstance(it, str):
            m = re.match(r"^declare\s+\S+\s+@(function_[0-9a-f]+)\(", it)
            if m:
                names.add(m.group(1))
    info = {}
    if phase in ("both", "callee"):
        for nm in sorted(names):
            if only and nm not in only:
                continue
            if not re.match(r"function_[0-9a-f]+$", nm):
                continue
            va = int(nm.split("_")[1], 16)
            rng = img.func_at(va)
            if rng is None:
                continue
            mf = MFunc(img, *rng)
            xp = xmm_params(mf)
            if not xp:
                continue
            # IR 側が既に xmm 引数を持つか (再実行 idempotent)
            have = False
            if nm in funcs:
                have = any(p[1].startswith("%xmm") for p in funcs[nm].params())
            info[nm] = dict(params=xp, have=have, mf=mf)
        stats["callees_with_xmm"] = len(info)
        stats["callees_pending"] = sum(1 for i in info.values() if not i["have"])
        log.append("F2 callee xmm live-in: " + ", ".join("%s:%s" % (n, {k: v[0] for k, v in i["params"].items()}) for n, i in info.items()))
        for nm, i in info.items():
            i["pty"] = {k: PTY[v[0]] for k, v in i["params"].items()}
    if phase == "callsite":
        # callsite 単独実行: callee 相で書換済みの define 引数から info を復元する
        for nm in sorted(names):
            if only and nm not in only:
                continue
            fn = funcs.get(nm)
            if fn is None:
                continue
            pmap = {}
            for p in fn.params():
                mm2 = re.match(r"^%xmm(\d+)_bits$", p[1])
                if mm2:
                    pmap[int(mm2.group(1))] = p[0]
            if not pmap:
                continue
            va = int(nm.split("_")[1], 16)
            rng = img.func_at(va)
            if rng is None:
                continue
            info[nm] = dict(params={k: (None, []) for k in pmap}, have=False, mf=MFunc(img, *rng), pty=pmap)
        stats["callees_with_xmm"] = len(info)
    if not repair:
        return stats
    # ---- callee の define/declare を書換 (call site 側が先に参照できるよう params 順を固定)
    for nm, i in (list(info.items()) if phase in ("both", "callee") else []):
        if i["have"]:
            continue
        fn = funcs.get(nm)
        ks = sorted(i["params"])
        extra = ", ".join("%s %%xmm%d_bits" % (PTY[i["params"][k][0]], k) for k in ks)
        if fn is not None:
            ix = FuncIndex(mod, fn)
            for k in ks:
                kind, readers = i["params"][k]
                hit = find_undef_for(mod, fn, ix, readers)
                if hit is None:
                    log.append("F2 %s: xmm%d の undef 値が見つからない (引数のみ追加)" % (nm, k))
                    stats["undef_missing"] = stats.get("undef_missing", 0) + 1
                    continue
                bi, li, name = hit
                pn = "%%xmm%d_bits" % k
                if kind == "f32" or kind == "f64":
                    fn.blocks[bi].lines[li] = "  %s = zext %s %s to i128" % (name, PTY[kind], pn)
                else:
                    fn.blocks[bi].lines[li] = "  %s = add i128 %s, 0" % (name, pn)
            m = IR.DEFINE.match(fn.sig)
            args = m.group(3).strip()
            newargs = (args + ", " + extra) if args else extra
            fn.sig = "define %s@%s(%s)%s{" % (m.group(1), nm, newargs, m.group(4))
        # declare の書換 (定義が無い callee, あるいは定義前に宣言が重複している場合)
        for idx, it in enumerate(mod.items):
            if isinstance(it, str):
                m = re.match(r"^(declare\s+\S+\s+@%s)\((.*?)\)(.*)$" % re.escape(nm), it)
                if m:
                    # 引数名付きで追加 (p1 領域の _lift_call が xmm 引数を識別するため)
                    ty = ", ".join("%s %%xmm%d_bits" % (PTY[i["params"][k][0]], k) for k in ks)
                    a = m.group(2).strip()
                    mod.items[idx] = "%s(%s)%s" % (m.group(1), (a + ", " + ty) if a else ty, m.group(3))
        stats["callee_fixed"] = stats.get("callee_fixed", 0) + 1
        log.append("F2 callee %s: + %s" % (nm, extra))
    # ---- call site
    if phase not in ("both", "callsite"):
        return stats
    for fn in mod.funcs():
        if not re.match(r"function_[0-9a-f]+$", fn.name):
            continue
        va = int(fn.name.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        callsites = []
        for bi, b in enumerate(fn.blocks):
            for li, ln in enumerate(b.lines):
                s = IR.strip_tokens(ln)
                m = re.search(r"\bcall\s+\S+\s+@(function_[0-9a-f]+)\((.*)\)\s*$", s)
                if m and m.group(1) in info and not info[m.group(1)]["have"]:
                    callsites.append((bi, li, m.group(1), s))
        if not callsites:
            continue
        mf = MFunc(img, *rng)
        done = []
        for (bi, li, callee, s0) in callsites:
            # 既に引数が揃っている call (p1 領域が lift した物等) は二重付与しない (LIFTLIB-2)
            cf = funcs.get(callee)
            ms = re.search(r"@%s\((.*)\)\s*$" % re.escape(callee), s0)
            if cf is not None and ms is not None and \
                    len([a for a in IR.split_args(ms.group(1)) if a.strip()]) == len(cf.params()):
                continue
            binder = Binder(mod, fn, mf, ix=(ix_map.get(fn.name) if ix_map else None))
            # 構造が変わらないので (bi, li) を補正しつつ処理
            shift = sum(n for (b2, l2, n) in done if b2 == bi and l2 <= li)
            li2 = li + shift
            ln = fn.blocks[bi].lines[li2]
            C = mod.addr_of(ln)
            if C is None:
                log.append("F2 call site of %s in %s: no insn.addr" % (callee, fn.name))
                stats["site_noaddr"] = stats.get("site_noaddr", 0) + 1
                continue
            ins, args = [], []
            tag = mod.tag(C)
            ok = True
            for k in sorted(info[callee]["params"]):
                pty = info[callee]["pty"][k]
                v = binder.bind("xmm%d" % k, C)
                if v is None or v[0].startswith("@@load:"):
                    log.append("F2 call %s@%x: xmm%d unbound" % (callee, C, k))
                    stats["site_unbound"] = stats.get("site_unbound", 0) + 1
                    ok = False
                    break
                nm_ = "%%f2_%x_x%d" % (C, k)
                if v[1] == pty:
                    args.append("%s %s" % (pty, v[0]))
                    continue
                w = {"i8": 8, "i16": 16, "i32": 32, "i64": 64, "i128": 128}
                if w.get(v[1], 0) > w[pty]:
                    ins.append("  %s = trunc %s %s to %s%s" % (nm_, v[1], v[0], pty, tag))
                else:
                    ins.append("  %s = zext %s %s to %s%s" % (nm_, v[1], v[0], pty, tag))
                args.append("%s %s" % (pty, nm_))
            if not ok:
                continue
            newln = re.sub(r"(@%s\()(.*?)(\)(?:\s*,\s*!insn\.addr !\d+)?\s*$)" % re.escape(callee),
                           lambda m: m.group(1) + (m.group(2) + ", " if m.group(2).strip() else "") + ", ".join(args) + m.group(3),
                           ln, count=1)
            fn.blocks[bi].lines[li2] = newln
            fn.blocks[bi].lines[li2:li2] = ins
            done.append((bi, li, len(ins)))
            stats["sites_fixed"] = stats.get("sites_fixed", 0) + 1
            log.append("F2 call %s@%x: + %s" % (callee, C, ", ".join(args)))
    return stats
