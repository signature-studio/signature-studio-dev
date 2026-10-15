"""iargs.py — [D3 (OTT) / HB-H3] RetDec の「整数引数レジスタ (rdx/r8/r9) 脱落」の検出と修復。

MS x64 ABI の整数引数は rcx/rdx/r8/r9。RetDec は
  - 呼出先が自前では引数 reg を読まず **さらに別の関数へ素通しする** (thunk / ctor の委譲)
  - 呼出元で r8d/r9d を `lea r8d,[r9-0x13]` / `mov r9d,0x14` で作る (結果が dead に見えて IR から消える)
と、その引数を IR から落とす (AudioEffect ctor の `function_180127550(this, 0, r8=1, r9=0x14)` が
`function_180127550(i64 %arg1)` に化け、AEffect.numPrograms/numParams が 0 になる — tools/ott/REPORT.md D3)。

機械語を正本に:
  1. 関数ごとの整数引数位置 live(f) = 自前 live-in (rcx..r9) + 直接 call/tail-jmp 先の live(g) のうち
     入口から素通しで届く引数 (推移閉包)。argc = max(live)+1。
  2. IR の define の仮引数が argc(f) より少なければ `i64 %argN` を追加 (declare も同様)。
  3. 全 call site で引数を接続し直す:
       - 引数位置 k の reg が **入口値のまま** (到達定義 = ENTRY) → 呼出元自身の `%arg{k+1}`
       - IR の引数が足りない位置 → 機械語の到達定義から値を bind (IR 値 / 即値 / lea 合成)
     bind できない site は 0 を渡し `site_unbound` に計上する (黙って 0 にしない: ログに site VA)。
スタック渡し (5 引数目以降) と xmm 引数 (f2) は扱わない。f2 より前に実行すること
(f2 は仮引数末尾に %xmmK_bits を足すので位置対応が崩れる)。
"""
import re

from .. import ir as IR
from ..mc import MFunc, GPR_ARGS, _canon_reg
from ..regbind import Binder, FuncIndex

FN_RE = re.compile(r"function_([0-9a-f]+)$")
CALL_RE = re.compile(r"\bcall\s+(\S+)\s+@(function_[0-9a-f]+)\((.*)\)\s*$")
W = {"i1": 1, "i8": 8, "i16": 16, "i32": 32, "i64": 64}
# 高バイト (bit 8-15) は _canon_reg で族の下位 8 bit と同じ正規化を受けるため、合成すると値を取り違える。
_HIGH8 = {"ah", "bh", "ch", "dh"}


def _va(name):
    m = FN_RE.match(name)
    return int(m.group(1), 16) if m else None


class Machine:
    """機械語側の整数引数 (推移閉包)。引数は「位置 k の集合」で持つ (callee が実際に読む reg だけが素通しする)。"""

    def __init__(self, img):
        self.img = img
        self._mf = {}
        self._live = {}

    def mf(self, va):
        if va not in self._mf:
            r = self.img.func_at(va)
            self._mf[va] = MFunc(self.img, *r) if r else None
        return self._mf[va]

    def calls(self, va):
        """直接 call / 関数外への tail-jmp: [(命令 va, target)]"""
        mf = self.mf(va)
        out = []
        for a in mf.order:
            it = mf.insns[a]
            if it.target is None:
                continue
            if it.is_call or (it.is_jmp and not (mf.start <= it.target < mf.end)):
                out.append((a, it.target))
        return out

    def live(self, va, _stack=()):
        """推移的に読まれる整数引数位置の集合 (frozenset of k)。None = 機械語が取れない。"""
        if va in self._live:
            return self._live[va]
        if va in _stack:
            return frozenset()
        mf = self.mf(va)
        if mf is None:
            return None
        li = mf.live_in()
        ks = {k for k, r in enumerate(GPR_ARGS) if r in li}
        for (a, t) in self.calls(va):
            g = self.live(t, _stack + (va,))
            for k in (g or ()):
                if 0 in mf.defs_before(a, GPR_ARGS[k]):      # 入口値が call に素通し
                    ks.add(k)
        r = frozenset(ks)
        if not _stack:
            self._live[va] = r
        return r

    def argc(self, va):
        l = self.live(va)
        if l is None:
            return None
        return (max(l) + 1) if l else 0


def _param_types(mod, fns, name):
    if name in fns:
        return [p[0] for p in fns[name].params()]
    d = mod.declares().get(name)
    if d is None:
        return None
    return [a.strip().split()[0] for a in IR.split_args(d[1]) if a.strip()]


def scan(mod, img, mach=None):
    """検出のみ。返値 dict:
      define_short : [(name, ir_params, machine_argc)]  — 仮引数が機械語より少ない define
      sites_short  : [(caller, site_va, callee, ir_args, machine_argc)] — 引数が足りない call site
      sites_entry  : [(caller, site_va, callee, k)] — 入口値が素通しなのに IR が別値 (undef 等) を渡す site
                     (IR に引数 k がある site のみ。引数が無い位置は sites_short 側)。run() の入口素通し修復と同じ判定:
                     機械語の到達定義が ENTRY のみ (defs_before == {0}) の位置 k で、IR の引数が呼出元自身の
                     `%arg{k+1}` でも run() 生成値 (`%ia_*`) でもないもの。
    """
    mach = mach or Machine(img)
    fns = {f.name: f for f in mod.funcs()}
    res = dict(define_short=[], sites_short=[], sites_entry=[], funcs=0)
    need = {}
    for nm, fn in fns.items():
        va = _va(nm)
        if va is None:
            continue
        c = mach.argc(va)
        if c is None:
            continue
        need[nm] = c
        res["funcs"] += 1
        n = len(fn.params())
        if all(re.match(r"%arg\d+$", p[1]) for p in fn.params()) and n < c:
            res["define_short"].append((nm, n, c))
    for nm, fn in fns.items():
        va = _va(nm)
        mf = mach.mf(va) if va is not None else None
        if mf is None:
            continue
        own_params = fn.params()
        own_named = all(re.match(r"%arg\d+$", p[1]) for p in own_params)
        own_n = max(len(own_params), need.get(nm, 0)) if own_named else len(own_params)
        for b in fn.blocks:
            for ln in b.lines:
                m = CALL_RE.search(IR.strip_tokens(ln))
                if not m:
                    continue
                g = m.group(2)
                C = mod.addr_of(ln)
                gv = _va(g)
                if C is None or gv is None:
                    continue
                gc = mach.argc(gv)
                if not gc:
                    continue
                cur = [a.strip() for a in IR.split_args(m.group(3)) if a.strip()]
                na = len(cur)
                if na < gc:
                    res["sites_short"].append((nm, C, g, na, gc))
                live = mach.live(gv) or frozenset()
                for k in sorted(live):
                    if k >= na or k >= own_n or mf.defs_before(C, GPR_ARGS[k]) != {0}:
                        continue
                    # run() が直す後の仮引数名 (define_short の呼出元は %arg{k+1} が追加される)
                    pnm = own_params[k][1] if k < len(own_params) else "%%arg%d" % (k + 1)
                    cur_tok = cur[k].split(None, 1)[-1]
                    if cur_tok != pnm and not cur_tok.startswith("%ia_"):
                        res["sites_entry"].append((nm, C, g, k))
    return res


class _Ctx:
    def __init__(self, mod, img):
        self.mod, self.img = mod, img
        self.fns = {f.name: f for f in mod.funcs()}
        self.mach = Machine(img)


def _conv(v, ty, want, tag, name, ins):
    """値 v (型 ty) を want 型へ (zext/trunc)。リテラルは型だけ変える。"""
    if ty == want:
        return v
    if re.match(r"^-?\d+$", str(v)):
        return str(v)
    if ty == "ptr":
        ins.append("  %s = ptrtoint ptr %s to i64%s" % (name + "p", v, tag))
        v, ty = name + "p", "i64"
        if want == "i64":
            return v
    if W[ty] > W[want]:
        ins.append("  %s = trunc %s %s to %s%s" % (name, ty, v, want, tag))
    else:
        ins.append("  %s = zext %s %s to %s%s" % (name, ty, v, want, tag))
    return name


def _entry_off(binder, mf, reg, va, depth=0):
    """va 直前の reg が入口 rsp からの相対アドレスなら、そのオフセットを返す (入口 rsp = 0)。
    形: `mov rax,rsp` (入口) → `lea rbp,[rax-K]` → reg。判定できなければ None。"""
    if depth > 4:
        return None
    r = binder.root_def(reg, va)
    if r == ("entry", "rsp"):
        return 0
    if r[0] != "def":
        return None
    it = mf.insns.get(r[1])
    if it is None or it.mnem != "lea" or not it.mem or it.mem["index"] or it.mem["rip"] is not None or it.mem["base"] in (None, "rsp"):
        return None
    b = _entry_off(binder, mf, it.mem["base"], r[1], depth + 1)
    return None if b is None else b + it.mem["disp"]


def _dom_at(ix, dpos, use):
    """IR 命令位置 dpos=(bi, li) の値が use=(bi, li) の位置で参照できるか (同一 block は行順, 他 block は支配)。"""
    (dbi, dli), (ubi, uli) = dpos, use
    if dbi == ubi:
        return dli < uli
    return ix.dominates(dbi, ubi)


def _bind_use(binder, reg, C, use):
    """reg の直前値 (bind) を、呼出し位置 use で参照できる形で返す (支配しない IR 値は使わない)。
    RetDec の phi 退避 (reg2mem alloca) で同じ値を覆う store があり、use を支配する load があれば、その reload を返す。
    どちらも無ければ None (呼出側が機械語から合成するか unbound にする)。use が None なら検査しない。"""
    v = binder.bind(reg, C)
    if use is None or v is None or str(v[0]).startswith("@@"):
        return v
    ix = binder.ix
    if v[0] not in ix.defs or _dom_at(ix, ix.defs[v[0]], use):
        return v
    for a, sts in ix.stores.items():
        if a not in ix.allocas or not any(vtok == v[0] for (_b, _l, vtok, _t) in sts):
            continue
        for (lbi, lli, dst) in ix.loads.get(a, []):
            if _dom_at(ix, (lbi, lli), use):
                return (dst, ix.allocas[a])
    return None


def _resolve(binder, mf, mod, reg, C, tag, nm, ins, depth=0, own_params=None, use=None):
    """C 直前の reg の値: (token, type) | None。IR 値が無い lea / add-sub imm は合成する。
    use=(bi, li) は値を参照する呼出し位置 (支配検査用)。"""
    v = _bind_use(binder, reg, C, use)
    if v is not None and not str(v[0]).startswith("@@"):
        return v
    if depth > 4:
        return None
    r = binder.root_def(reg, C)
    if r[0] != "def":
        return None
    d, rg = r[1], r[2]
    it = mf.insns.get(d)
    if it is None or len(it.ops) != 2 or it.ops[0].type != 1:
        return None
    w = it.ops[0].size * 8
    ty = "i64" if w == 64 else "i%d" % w
    if it.mnem == "mov" and it.mem and it.mem["base"] not in (None, "rsp", "rip") and it.mem["index"] is None and it.mem["read"] and w in (32, 64) and own_params:
        # 入口 rsp+0x28 以上 = 呼出元自身の 5 番目以降の引数 (%arg{k+1}, k>=4)。MS x64 の積み位置。
        base_off = _entry_off(binder, mf, it.mem["base"], d)
        off = None if base_off is None else base_off + it.mem["disp"]
        if off is not None and off >= 0x28 and (off - 0x28) % 8 == 0 and (off - 0x28) // 8 + 4 < len(own_params):
            pty, pnm = own_params[(off - 0x28) // 8 + 4]
            if pnm.startswith("%arg"):
                return (pnm, pty)
    if it.mnem == "mov" and it.mem and it.mem["rip"] is not None and it.mem["read"] and w in (32, 64):
        ins.append("  %s = load %s, ptr inttoptr (i64 %d to ptr)%s" % (nm + "m", ty, it.mem["rip"], tag))
        return (nm + "m", ty)
    if it.mnem == "movzx" and it.ops[1].type == 1 and w in (32, 64):
        if it._ci.reg_name(it.ops[1].reg) in _HIGH8:
            return None
        src = _canon_reg(it._ci, it.ops[1].reg)
        sw = it.ops[1].size * 8
        base = _resolve(binder, mf, mod, src, d, tag, nm + "v", ins, depth + 1, use=use)
        if base is None:
            return None
        if re.match(r"^-?\d+$", str(base[0])):
            return (str(int(base[0]) & ((1 << sw) - 1)), ty)
        if base[1] not in W:
            return None
        src_ty = "i%d" % sw
        t = _conv(base[0], base[1], src_ty, tag, nm + "mt", ins)
        return (_conv(t, src_ty, ty, tag, nm + "mz", ins), ty)
    if it.mnem == "lea" and it.mem and not it.mem["index"] and it.mem["base"] not in (None, "rip", "rsp"):
        base = _resolve(binder, mf, mod, it.mem["base"], d, tag, nm + "b", ins, depth + 1, use=use)
        if base is None:
            return None
        disp = it.mem["disp"]
        if re.match(r"^-?\d+$", str(base[0])):
            x = int(base[0]) + disp
            if w < 64:
                x &= (1 << w) - 1
            return (str(x), ty)
        if base[1] != ty:
            b2 = _conv(base[0], base[1], ty, tag, nm + "c", ins)
            base = (b2, ty)
        ins.append("  %s = add %s %s, %d%s" % (nm + "s", ty, base[0], disp, tag))
        return (nm + "s", ty)
    return None


def run(mod, img, log=None, stats=None, repair=True):
    log = log if log is not None else []
    stats = stats if stats is not None else {}
    cx = _Ctx(mod, img)
    mach, fns = cx.mach, cx.fns
    need = {}
    for nm in fns:
        va = _va(nm)
        if va is None:
            continue
        c = mach.argc(va)
        if c is not None:
            need[nm] = c
    # 宣言のみの callee も対象 (仮引数を足す)
    for nm in mod.declares():
        va = _va(nm)
        if va is not None and nm not in need:
            c = mach.argc(va)
            if c is not None:
                need[nm] = c
    pre = scan(mod, img, mach)
    stats["funcs"] = pre["funcs"]
    stats["define_short"] = len(pre["define_short"])
    stats["sites_short"] = len(pre["sites_short"])
    if not repair:
        return stats
    # ---- 1. define / declare の仮引数追加
    ptys = {}
    for nm, c in need.items():
        fn = fns.get(nm)
        if fn is not None:
            ps = fn.params()
            if any(not re.match(r"%arg\d+$", p[1]) for p in ps):
                log.append("iargs %s: 非 %%argN 仮引数あり (f2 後?) — skip" % nm)
                continue
            n = len(ps)
            if n < c:
                extra = ", ".join("i64 %%arg%d" % (k + 1) for k in range(n, c))
                m = IR.DEFINE.match(fn.sig)
                args = m.group(3).strip()
                fn.sig = "define %s@%s(%s)%s{" % (m.group(1), nm, (args + ", " + extra) if args else extra, m.group(4))
                stats["define_fixed"] = stats.get("define_fixed", 0) + 1
                log.append("iargs define %s: + %s" % (nm, extra))
            ptys[nm] = [p[0] for p in fn.params()]
    for idx, it in enumerate(mod.items):
        if not isinstance(it, str):
            continue
        m = re.match(r"^(declare\s+\S+\s+@(function_[0-9a-f]+))\((.*?)\)(.*)$", it)
        if not m or m.group(2) not in need or m.group(2) in fns:
            continue
        nm = m.group(2)
        cur = [a for a in IR.split_args(m.group(3)) if a.strip()]
        if len(cur) < need[nm]:
            ty = ", ".join(["i64"] * (need[nm] - len(cur)))
            mod.items[idx] = "%s(%s)%s" % (m.group(1), (m.group(3).strip() + ", " + ty) if m.group(3).strip() else ty, m.group(4))
            stats["declare_fixed"] = stats.get("declare_fixed", 0) + 1
        ptys[nm] = [a.strip().split()[0] for a in IR.split_args(re.match(r"^declare\s+\S+\s+@\S+?\((.*?)\)", mod.items[idx]).group(1)) if a.strip()]
    # ---- 2. call site の引数接続
    for fn in mod.funcs():
        va = _va(fn.name)
        if va is None:
            continue
        mf = mach.mf(va)
        if mf is None:
            continue
        sites = []
        for bi, b in enumerate(fn.blocks):
            for li, ln in enumerate(b.lines):
                m = CALL_RE.search(IR.strip_tokens(ln))
                if m and m.group(2) in need and need[m.group(2)]:
                    sites.append((bi, li, m.group(2)))
        if not sites:
            continue
        own_params = fn.params()
        binder = None
        shift = {}
        for (bi, li, g) in sites:
            li2 = li + shift.get(bi, 0)
            ln = fn.blocks[bi].lines[li2]
            C = mod.addr_of(ln)
            if C is None:
                stats["site_noaddr"] = stats.get("site_noaddr", 0) + 1
                continue
            s0 = IR.strip_tokens(ln)
            ms = re.search(r"@%s\((.*)\)\s*$" % re.escape(g), s0)
            cur = [a.strip() for a in IR.split_args(ms.group(1)) if a.strip()]
            gty = ptys.get(g) or ["i64"] * need[g]
            if binder is None:
                binder = Binder(mod, fn, mf)
            tag = mod.tag(C)
            ins, newargs, changed = [], list(cur), False
            live = mach.live(_va(g)) or frozenset()
            for k in range(need[g]):
                want = gty[k] if k < len(gty) else "i64"
                reg = GPR_ARGS[k]
                nm_ = "%%ia_%x_%d" % (C, k)
                if k >= len(cur):
                    newargs.append("%s 0" % want)             # callee が読まない位置の穴埋め
                    changed = True
                if k not in live:
                    continue
                ds = mf.defs_before(C, reg)
                if ds == {0}:
                    # 入口値が素通し: 呼出元自身の仮引数 (RetDec は undef/別値を渡している)
                    if k < len(own_params):
                        pty, pnm = own_params[k]
                        cur_tok = newargs[k].split(None, 1)[-1]
                        if cur_tok != pnm and not cur_tok.startswith("%ia_"):       # %ia_* = 前回生成した値 (冪等)
                            tok = _conv(pnm, pty, want, tag, nm_, ins)
                            newargs[k] = "%s %s" % (want, tok)
                            changed = True
                            stats["args_entry_fixed"] = stats.get("args_entry_fixed", 0) + 1
                    continue
                if k < len(cur):
                    continue
                v = _resolve(binder, mf, mod, reg, C, tag, nm_, ins, own_params=own_params, use=(bi, li))
                if v is None:
                    stats["site_unbound"] = stats.get("site_unbound", 0) + 1
                    log.append("iargs call %s@%x: %s unbound (0 を渡す)" % (g, C, reg))
                    continue
                tok = _conv(v[0], v[1], want, tag, nm_ + "z", ins)
                newargs[k] = "%s %s" % (want, tok)
                stats["args_added"] = stats.get("args_added", 0) + 1
            if not changed:
                continue
            newln = re.sub(r"(@%s\()(.*)(\)(?:\s*,\s*!insn\.addr !\d+)?\s*$)" % re.escape(g),
                           lambda m: m.group(1) + ", ".join(newargs) + m.group(3), ln, count=1)
            fn.blocks[bi].lines[li2] = newln
            fn.blocks[bi].lines[li2:li2] = ins
            shift[bi] = shift.get(bi, 0) + len(ins)
            stats["sites_fixed"] = stats.get("sites_fixed", 0) + 1
            log.append("iargs call %s@%x: (%s) -> (%s)" % (g, C, ", ".join(cur), ", ".join(newargs)))
    return stats
