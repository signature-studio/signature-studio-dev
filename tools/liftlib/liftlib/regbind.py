"""regbind.py — 機械語レジスタ ↔ IR SSA 値の結合 (insn.addr 経由)。

RetDec IR の各命令は `!insn.addr !N` で機械語 VA に紐づく。これを使い
  bind(reg, va)  : 命令 va の直前時点で reg が保持する値を表す IR 値 (名前と型) を返す
を実現する。到達定義は mc.MFunc、IR 側定義は本モジュールの索引から。
  - 単一定義 d      → d に注釈された IR 命令のうち reg の幅に合う型の最後の def
  - 関数入口 (ENTRY) → GPR 引数は %argN, xmm は %xmmK_bits (f2 付与があれば), それ以外は None
  - 複数定義 (phi)   → RetDec の reg2mem alloca のうち, 各定義値を全て store している alloca を探し,
                        その alloca を load する (支配する既存 load を優先)
  - IR に現れない定数系 def (xor/sub 自己ゼロ化, mov/movabs 即値) は値を合成する (CAB-239)。
"""
import re

from . import ir as IR
from .mc import GPR_ARGS

TYPE_BITS = {"i1": 1, "i8": 8, "i16": 16, "i32": 32, "i64": 64, "i128": 128}
_CAST_OPS = ("zext", "sext", "trunc", "bitcast", "inttoptr", "ptrtoint", "fpext", "fptrunc", "sitofp",
             "uitofp", "fptosi", "fptoui")
_ATTRS = r"(?:(?:nuw|nsw|exact|inbounds|nonnull|noundef|disjoint|fast|nnan|ninf|nsz|volatile|tail|notail|musttail)\s+)*"
DEF_RE = re.compile(r"^\s*(%[\w$.\-]+) = " + _ATTRS + r"(\w+)\s+(.*)$")


def result_type(line):
    """代入行 `%x = ...` の結果型 (文字列)。判別不能なら None。"""
    m = DEF_RE.match(IR.strip_tokens(line))
    if not m:
        return None
    op, rest = m.group(2), m.group(3)
    if op in _CAST_OPS:
        mm = re.search(r"\sto\s+(\S+?)\s*$", rest)
        return mm.group(1) if mm else None
    if op in ("icmp", "fcmp"):
        return "i1"
    if op == "load":
        return rest.split(",")[0].strip()
    if op == "call":
        # call <ty> @f(...)  / call <ty> (ptr...) %f(...)
        mm = re.match(r"((?:\w+\s+)*?)(i\d+|ptr|float|double|void|\{[^}]*\}|<[^>]*>)\s+(?:\(.*\)\s+)?@", rest)
        if mm:
            return mm.group(2)
        mm = re.match(r"(i\d+|ptr|float|double|void)\b", rest)
        return mm.group(1) if mm else None
    if op in ("alloca",):
        return "ptr"
    if op == "select":
        mm = re.search(r",\s*(i\d+|ptr|float|double)\s+\S+,\s*(i\d+|ptr|float|double)\s+\S+\s*$", rest)
        return mm.group(1) if mm else None
    if op == "phi":
        return rest.split()[0]
    return rest.split()[0].rstrip(",")


class FuncIndex:
    """IR 関数の索引 (addr → 命令, 名前 → 定義位置, alloca ストア)。"""

    def __init__(self, mod, fn):
        self.mod, self.fn = mod, fn
        self.by_addr = {}      # va -> [(bi, li)]
        self.defs = {}         # %name -> (bi, li)
        self.allocas = {}      # %name -> type
        self.stores = {}       # alloca name -> [(bi, li, value_token)]
        self.loads = {}        # alloca name -> [(bi, li, %dst)]
        for bi, b in enumerate(fn.blocks):
            for li, ln in enumerate(b.lines):
                va = mod.addr_of(ln)
                if va is not None:
                    self.by_addr.setdefault(va, []).append((bi, li))
                d = IR.instr_dst(ln)
                if d:
                    self.defs[d] = (bi, li)
                    m = re.match(r"^\s*%[\w$.\-]+ = alloca ([^\s,]+)", ln)
                    if m:
                        self.allocas[d] = m.group(1)
                m = re.match(r"^\s*store (\S+) (\S+?), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
                if m:
                    self.stores.setdefault(m.group(3), []).append((bi, li, m.group(2), m.group(1)))
                m = re.match(r"^\s*(%[\w$.\-]+) = load (\S+), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
                if m:
                    self.loads.setdefault(m.group(3), []).append((bi, li, m.group(1)))
        self.label_idx = {b.label: i for i, b in enumerate(fn.blocks)}

    def instrs_at(self, va):
        return [(bi, li, self.fn.blocks[bi].lines[li]) for (bi, li) in self.by_addr.get(va, [])]

    def has_label(self, va):
        return ("dec_label_pc_%x" % va) in self.label_idx

    def present(self, va):
        return bool(self.by_addr.get(va)) or self.has_label(va)

    # ---- CFG / dominance (IR) ---------------------------------------------
    def succs(self, bi):
        b = self.fn.blocks[bi]
        out = []
        for ln in b.lines:
            s = IR.strip_tokens(ln)
            if re.match(r"^\s*(br|switch|ret|unreachable|indirectbr)\b", s):
                for lab in re.findall(r"label %([\w$.\-]+)", s):
                    if lab in self.label_idx:
                        out.append(self.label_idx[lab])
        return out

    def dominators(self):
        if hasattr(self, "_dom"):
            return self._dom
        n = len(self.fn.blocks)
        succ = [self.succs(i) for i in range(n)]
        pred = [[] for _ in range(n)]
        for i, ss in enumerate(succ):
            for s in ss:
                pred[s].append(i)
        full = set(range(n))
        dom = [set(full) for _ in range(n)]
        dom[0] = {0}
        ch = True
        while ch:
            ch = False
            for i in range(1, n):
                if not pred[i]:
                    continue
                new = set(full)
                for p in pred[i]:
                    new &= dom[p]
                new |= {i}
                if new != dom[i]:
                    dom[i] = new
                    ch = True
        self._dom = dom
        return dom

    def dominates(self, a, b):
        """ブロック a がブロック b を支配するか。"""
        return a in self.dominators()[b]


def bits_of(tok_type):
    return TYPE_BITS.get(tok_type)


class Binder:
    def __init__(self, mod, fn, mf, ix=None):
        self.mod, self.fn, self.mf = mod, fn, mf
        self.ix = ix if ix is not None else FuncIndex(mod, fn)
        self.params = fn.params()          # [(type, %name)]
        self.notes = []
        self._xmm0_ret = {}               # callee VA -> True/False/None (未決) のキャッシュ

    # ---- xmm0 戻り関数の判定 (LIFTLIB-3 汎用 xmm0-ret bind) -------------------
    def callee_returns_xmm0(self, target):
        """callee が xmm0 に double bits を返す (結果を xmm0 へ書く) と推定する。

        命名規則 (関数名・C port 名) に依存せず, callee の機械語だけで決める:
          1. 全 `ret` ブロックで xmm0 の到達定義が関数内 (ENTRY でない) = 値を書いて返す
          2. 入口で xmm0 が引数として live-in (読まれる) — 読み取り専用/参照渡しは除外
          3. 戻り先 (call site) で xmm0 が call 後に読まれる (結果を消費する)
        の 3 条件。判定不能 (命令が取れない等) は None (= 使わない)。
        """
        if target in self._xmm0_ret:
            return self._xmm0_ret[target]
        r = None
        try:
            rng = self.mf.img.func_at(target)
            if rng is not None:
                from .mc import MFunc
                cmf = MFunc(self.mf.img, *rng)
                rets = [va for va in cmf.order if cmf.insns[va].is_ret]
                if rets:
                    ok = all(cmf.defs_before(v, "xmm0") and 0 not in cmf.defs_before(v, "xmm0")
                             for v in rets)
                    live = cmf.live_in()
                    ok = ok and ("xmm0" in live)
                else:
                    ok = False
                if ok:
                    r = True
                else:
                    r = False
        except Exception:                # noqa — 判定不能は「使わない」
            r = None
        self._xmm0_ret[target] = r
        return r

    def xmm0_ret_of_call(self, va):
        """call 命令 va の戻りが xmm0 (double bits) と推定できるなら True。"""
        it = self.mf.insns.get(va)
        if it is None or not it.is_call or it.target is None:
            return False
        return bool(self.callee_returns_xmm0(it.target))

    # ---- 値の def 検索 ----------------------------------------------------
    # p1 が領域を再構成すると「同一機械語アドレスに対応する IR 命令が 2 本」になる
    # (原本 block のもの + 領域 block の `%p1r_…` を dst にするもの)。従来は末尾
    # (= 領域側) を拾っていたが, 領域値は経路固有 SSA を持つため他経路から参照すると
    # 非支配 (clang "does not dominate all uses") になり, p1 が「非支配/他領域」で
    # 落としていた (LIFTLIB-4: bind xmm1 5 件のうち 3 件がこの形)。
    # 注意: 領域 block の **ラベル** は `dec_label_pc_<va>` で原本と区別できないので,
    # dst の SSA 名 (`%p1r_` / `%p1tail_` / `%p1relay_` / `%p1srelay_`) で判別する。
    _REGION_DST = ("%p1r_", "%p1tail_", "%p1relay_", "%p1srelay_")

    def _is_region_dst(self, name):
        return isinstance(name, str) and name.startswith(self._REGION_DST)

    def value_defined_at(self, reg, va):
        """命令 va で reg に書かれた値を表す IR (name, type)。

        LIFTLIB-3: reg が xmm0 で, va が xmm0 戻り callee への call のとき, call の
        i64/i32 戻り (rax) を xmm0 のビット列として拾う (従来は明示的 C port 名のみ)。
        LIFTLIB-4: 同一アドレスに原本/領域の 2 命令が在るとき原本を優先する (上記参照)。
        """
        want_xmm = reg.startswith("xmm")
        orig, last = None, None
        for (bi, li, ln) in self.ix.instrs_at(va):
            d = IR.instr_dst(ln)
            if not d:
                continue
            ty = result_type(ln)
            if want_xmm:
                if ty == "i128":
                    ok = True
                elif ty in ("i64", "i32") and self.xmm0_ret_of_call(va):
                    ok = True              # xmm0 bits = i64 戻り (zext は呼出側で)
                else:
                    ok = False
            else:
                ok = ty in ("i64", "i32", "i16", "i8")
            if not ok:
                continue
            last = (d, ty)
            if not self._is_region_dst(d):
                orig = (d, ty)              # 原本側を記憶 (後の領域命令で上書きしない)
        return orig if orig is not None else last

    def _is_copy(self, va):
        it = self.mf.insns.get(va)
        if it is None:
            return None
        if it.mnem == "mov" and len(it.ops) == 2 and it.ops[0].type == 1 and it.ops[1].type == 1:
            from .mc import _canon_reg
            return _canon_reg(it._ci, it.ops[1].reg)
        return None

    def root_def(self, reg, va, depth=0):
        """reg の直前定義を reg-reg mov を辿って解決: ('entry', reg) | ('def', addr, reg) | ('multi', set)"""
        defs = self.mf.defs_before(va, reg)
        if len(defs) != 1:
            return ("multi", defs, reg)
        (d,) = defs
        if d == 0:
            return ("entry", reg)
        src = self._is_copy(d)
        if src and depth < 8:
            return self.root_def(src, d, depth + 1)
        return ("def", d, reg)

    def bind(self, reg, va):
        """命令 va の直前の reg を IR 値で返す: (name_or_const, type) | None。"""
        r = self.root_def(reg, va)
        if r[0] == "entry":
            if r[1] in GPR_ARGS:
                k = GPR_ARGS.index(r[1])
                if k < len(self.params):
                    return (self.params[k][1], self.params[k][0])
            if r[1].startswith("xmm"):
                # f2 pass が付与した %xmmK_bits 引数があれば入口 xmm 値として使う (CAB-239)
                k = int(r[1][3:])
                for ty, nm in self.params:
                    if nm == "%%xmm%d_bits" % k:
                        return (nm, ty)
            return None
        if r[0] == "def":
            v = self.value_defined_at(r[2], r[1])
            if v is not None:
                return v
            return self.synthetic_def(r[2], r[1])
        # multi: reg2mem alloca を探す
        return self._bind_multi(r[2], r[1], va)

    def bind_relaxed(self, reg, va):
        """多定義 bind の緩和 (LIFTLIB-2): IR 値を持たない def (= 落とされた経路の def) が
        未覆でも, 残りの def を store で覆う reg2mem alloca があればそれを読む。

        alloca の内容 = 生存側経路の store (領域側の値は p1 の relay store / reg2mem 合成が
        同一 alloca に書く)。落とされた経路の def が IR 値を持つ場合は緩和しない
        (誤った経路の値を選ぶ危険が高いため)。"""
        r = self.root_def(reg, va)
        if r[0] != "multi":
            return None
        return self._bind_multi(r[2], r[1], va, relaxed=True)

    def synthetic_def(self, reg, va):
        """RetDec IR に現れない定数系 def (xor/sub 自己ゼロ化, mov/movabs 即値) の値を合成する。

        call を跨ぐ callee-saved reg (r15/rbx 等) がプロローグのゼロ化/即値 mov だけで
        定義されている場合, IR 側に対応行が無く bind に失敗していた (CAB-239 語彙拡張)。
        """
        it = self.mf.insns.get(va)
        if it is None:
            return None
        m, ops = it.mnem, it.ops
        want_xmm = reg.startswith("xmm")
        if m in ("mov", "movabs") and len(ops) == 2 and ops[0].type == 1 and ops[1].type == 2 \
                and not want_xmm:
            w = ops[0].size * 8
            imm = ops[1].imm
            if w < 64:
                imm &= (1 << w) - 1
            elif imm >= (1 << 63):
                imm -= (1 << 64)
            return (str(imm), "i64" if w == 64 else "i%d" % w)
        if not want_xmm and m in ("xor", "sub") and len(ops) == 2 \
                and ops[0].type == 1 and ops[0].reg == ops[1].reg:
            w = ops[0].size * 8
            return ("0", "i64" if w == 64 else "i%d" % w)
        if want_xmm and m.lstrip("v") in ("xorps", "xorpd", "pxor") and len(ops) >= 2 \
                and ops[0].type == 1 and ops[0].reg == ops[-1].reg:
            return ("0", "i128")
        return None

    def _bind_multi(self, reg, defs, va, relaxed=False):
        want = set(defs)
        ix = self.ix
        best = None
        for a, sts in ix.stores.items():
            if a not in ix.allocas:
                continue
            covered = set()
            for (bi, li, vtok, vty) in sts:
                if vtok.startswith("%") and vtok in ix.defs:
                    dbi, dli = ix.defs[vtok]
                    covered.add(self.mod.addr_of(ix.fn.blocks[dbi].lines[dli]))
                    # load alloca → alloca 経由の再 store もたどる (1 段)
                    ln = ix.fn.blocks[dbi].lines[dli]
                    mm = re.match(r"^\s*%[\w$.\-]+ = load \S+, ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
                    if mm and mm.group(1) in ix.stores:
                        for (b2, l2, v2, t2) in ix.stores[mm.group(1)]:
                            if v2 in ix.defs:
                                d2 = ix.defs[v2]
                                covered.add(self.mod.addr_of(ix.fn.blocks[d2[0]].lines[d2[1]]))
            # 入口 (ENTRY=0) は callee-saved reg の入口値 (ハーネス側で 0 初期化) として
            # alloca 未初期化読み (B1 後 0) と整合させる (CAB-239)
            eff = want - {0}
            if relaxed:
                # 緩和: 未覆 def が「IR 値を持たない (落とされた経路の) def」のみなら許す
                unc = eff - covered
                if not unc or not (eff & covered):
                    continue
                if any(self.value_defined_at(reg, d) is not None and self.synthetic_def(reg, d) is not None
                       for d in unc if d):
                    continue
                if best is None or len(covered & eff) > len(best[2] & best[1]):
                    best = (a, eff, covered)
            elif eff and eff <= covered:
                if best is None or len(covered) < len(best[1]):
                    best = (a, covered)
        if best is None and reg == "xmm0":
            # LIFTLIB-3 フォールバック: def のうち xmm0 戻り callee への call が 1 つでも
            # あれば, 複数経路の合流値を「最後に call した結果」と見なせる場合に限り採る。
            # (def 集合が「同一 call の前後 (ENTRY 含む) 」= 実質その call の戻り, 例 tan 0x1801a9e39)
            calls = [d for d in want if d and self.mf.insns.get(d) is not None
                     and self.mf.insns[d].is_call and self.xmm0_ret_of_call(d)]
            if calls and len(calls) == 1:
                v = self.value_defined_at("rax", calls[-1])
                if v is not None and v[1] in ("i64", "i32"):
                    return v                 # call の i64/i32 戻り = xmm0 bits
        if best is None:
            return None
        a = best[0]
        ty = ix.allocas[a]
        # va を含む IR ブロックを支配する load を探す
        tgt = self.block_containing(va)
        for (bi, li, dst) in ix.loads.get(a, []):
            if tgt is not None and ix.dominates(bi, tgt):
                return (dst, ty)
        return ("@@load:" + a, ty)       # 呼出側が新規 load を挿入

    def block_containing(self, va):
        """機械語 va に対応する IR ブロック index (最寄りの注釈命令/ラベル)。"""
        ix = self.ix
        if ix.by_addr.get(va):
            return ix.by_addr[va][0][0]
        # va 以前で最大の注釈アドレスを持つ IR 位置
        best, bb = None, None
        for a, lst in ix.by_addr.items():
            if a <= va and (best is None or a > best):
                best, bb = a, lst[0][0]
        for lab, bi in ix.label_idx.items():
            m = re.match(r"dec_label_pc_([0-9a-f]+)$", lab or "")
            if m:
                a = int(m.group(1), 16)
                if a <= va and (best is None or a >= best):
                    best, bb = a, bi
        return bb
