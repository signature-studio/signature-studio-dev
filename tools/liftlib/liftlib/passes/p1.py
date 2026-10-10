"""p1.py — [P1] comis/ucomis 後の分岐の再配線・再構成 (名前/VA/サフィックス非依存)。

RetDec は `comisd/ucomisd/comiss/ucomiss` を `call void @__asm_*comis*(a, b)` (フラグ副作用なし) と lift する。
このため後続の `jcc` は
  (1) CF/ZF/PF が無関係な前段 cmp の SSA に誤結線される    → "miswired"  (KH Gain [P1], OTT br_cf/br_zf)
  (2) フラグが undef 扱いで分岐が畳み込まれ片側が脱落する   → "dropped"   (FA Gain [P1'], OTT no_branch 66/94)
の 2 型で壊れる。本 pass は **機械語 (capstone) を正本**として
  - comis 命令と、そのフラグを消費する jcc を特定 (到達定義 flags)
  - IR 側で jcc の `br` (insn.addr = jcc の VA) を引き当て
  - 条件を fcmp から再構成して差し替え (miswired)。ラベルの向きは機械語の taken 先 (T) で決める
  - br が無い (dropped) 場合は機械語の脱落側断片を mini-lifter で IR 化して分岐を再構成
する。解釈不能な形は `unsupported` として報告する (黙って変えない)。
"""
import re

from .. import ir as IR
from ..mc import MFunc, _canon_reg
from ..regbind import Binder, FuncIndex, result_type

# jcc の condition code -> (fcmp predicate, 反転か)
#   comis: unordered => CF=ZF=PF=1, a<b => CF=1, a==b => ZF=1, a>b => 全 0
CC_PRED = {
    "b": "ult", "c": "ult", "nae": "ult",
    "ae": "oge", "nb": "oge", "nc": "oge",
    "e": "ueq", "z": "ueq",
    "ne": "one", "nz": "one",
    "be": "ule", "na": "ule",
    "a": "ogt", "nbe": "ogt",
    "p": "uno", "pe": "uno",
    "np": "ord", "po": "ord",
}

COMIS_CALL = re.compile(r"call void @(__asm_v?u?comis([sd])(?:__\w+|\.\d+)?)\((.*)\)")


def label_target(label):
    """IR ラベル -> 機械語アドレス (crit_edge は行き先側)。"""
    hs = re.findall(r"dec_label_pc_([0-9a-f]+)", label or "")
    if not hs:
        return None
    if "crit_edge" in label and len(hs) > 1:
        return int(hs[-1], 16)
    return int(hs[0], 16)


def parse_comis_call(line):
    s = IR.strip_tokens(line)
    m = COMIS_CALL.search(s)
    if not m:
        return None
    kind = m.group(2)
    args = IR.split_args(m.group(3))
    if len(args) != 2:
        return None
    return kind, args[0], args[1]


class SiteReport(dict):
    pass


def flag_consumers(mf, A):
    """comis A のフラグを消費する命令 (jcc / setcc / cmovcc / adc / sbb ...) のリスト。
    A -> 直線的に前進し flags を読む命令を拾う (flags を再定義する命令で打切り)。"""
    out = []
    blocks = mf.cfg()
    # 到達定義: flags の def が {A} だけの読み手
    for va in mf.order:
        it = mf.insns[va]
        if "flags" in it.reads and va > A:
            d = mf.defs_before(va, "flags")
            if d == {A}:
                out.append(va)
    return out


def analyze(mod, fn, mf, binder):
    ix = binder.ix
    sites = []
    for A in mf.comis_sites():
        rec = SiteReport(A=A, consumers=[], call=None, status="")
        calls = [(bi, li, ln) for (bi, li, ln) in ix.instrs_at(A) if COMIS_CALL.search(IR.strip_tokens(ln))]
        rec["call"] = calls[0] if calls else None
        for J in flag_consumers(mf, A):
            it = mf.insns[J]
            c = dict(J=J, mnem=it.mnem)
            if it.is_jcc:
                c["kind"] = "jcc"
                c["T"], c["F"] = it.target, it.next
                c["cc"] = it.cc
                brs = [(bi, li, ln) for (bi, li, ln) in ix.instrs_at(J)
                       if re.match(r"^\s*br\b", IR.strip_tokens(ln))]
                conds = [x for x in brs if re.match(r"^\s*br i1 ", IR.strip_tokens(x[2]))]
                if conds:
                    c["state"] = "branch"
                    c["br"] = conds[0]
                    mt = re.match(r"^\s*br i1 (%[\w$.\-]+),", IR.strip_tokens(conds[0][2]))
                    if mt and mt.group(1).startswith("%p1r_"):
                        c["state"] = "region_done"   # 別 site の region が既に再構成済み (CAB-239)
                elif brs:
                    c["state"] = "folded"            # br label X だけに畳まれている
                    c["br"] = brs[0]
                else:
                    c["state"] = "dropped"
            else:
                c["kind"] = "other"
                c["state"] = "unsupported"
            rec["consumers"].append(c)
        sites.append(rec)
    return sites


def _fresh(tag, A, n):
    return "%%p1_%x_%s%d" % (A, tag, n)


def build_compare(mod, A, call_line, kind, sfx=""):
    """comis 呼出の引数から a, b (double/float) を作る命令列を返す: (instrs, a_name, b_name, fty)"""
    pc = parse_comis_call(call_line)
    _k, a1, a2 = pc
    ty = "double" if kind == "d" else "float"
    ity = "i64" if kind == "d" else "i32"
    tag = mod.tag(A)
    ins = []
    t1 = a1.split(None, 1)
    if t1[0] != "i128":
        return None
    ins.append("  %%p1_%x%s_ta = trunc i128 %s to %s%s" % (A, sfx, t1[1], ity, tag))
    ins.append("  %%p1_%x%s_fa = bitcast %s %%p1_%x%s_ta to %s%s" % (A, sfx, ity, A, sfx, ty, tag))
    t2 = a2.split(None, 1)
    if t2[0] == "i128":
        ins.append("  %%p1_%x%s_tb = trunc i128 %s to %s%s" % (A, sfx, t2[1], ity, tag))
        ins.append("  %%p1_%x%s_fb = bitcast %s %%p1_%x%s_tb to %s%s" % (A, sfx, ity, A, sfx, ty, tag))
    elif t2[0] == ity:
        ins.append("  %%p1_%x%s_fb = bitcast %s %s to %s%s" % (A, sfx, ity, t2[1], ty, tag))
    elif t2[0] in ("i64", "i32"):
        # 幅違い (ss なのに i64 等): trunc/bitcast
        if t2[0] == "i64" and ity == "i32":
            ins.append("  %%p1_%x%s_tb = trunc i64 %s to i32%s" % (A, sfx, t2[1], tag))
            ins.append("  %%p1_%x%s_fb = bitcast i32 %%p1_%x%s_tb to %s%s" % (A, sfx, A, sfx, ty, tag))
        else:
            return None
    else:
        return None
    return ins, "%%p1_%x%s_fa" % (A, sfx), "%%p1_%x%s_fb" % (A, sfx), ty


def orient(br_line, T, F, cond):
    """br i1 の true/false ラベルが機械語の taken(T)/fallthrough(F) のどちらかを判定し,
    差し替え条件を返す: (新条件トークン, 追加命令) | None"""
    s = IR.strip_tokens(br_line)
    m = re.match(r"^\s*br i1 (\S+), label %([\w$.\-]+), label %([\w$.\-]+)", s)
    if not m:
        return None
    lt, lf = label_target(m.group(2)), label_target(m.group(3))
    if lt == T and lf != T:
        return "pos"
    if lf == T and lt != T:
        return "neg"
    if lt == F and lf != F:
        return "neg"
    if lf == F and lt != F:
        return "pos"
    return None


def rewire(mod, fn, ctx, rec, c, stats, ix_rebuild):
    """miswired / folded でない通常の br i1: 条件を fcmp で差し替え。"""
    bi, li, ln = c["br"]
    A = rec["A"]
    cb, cl, call_ln = rec["call"]
    kind = parse_comis_call(call_ln)[0]
    pred = CC_PRED.get(c["cc"])
    if pred is None:
        stats["unsupported_cc"] = stats.get("unsupported_cc", 0) + 1
        return False
    o = orient(ln, c["T"], c["F"], None)
    if o is None:
        stats["unresolved_orient"] = stats.get("unresolved_orient", 0) + 1
        return False
    # compare は br の直前に (J ごとに名前を分ける) — comis block が br block を支配しない場合でも安全
    bc = build_compare(mod, A, call_ln, kind, sfx="%x" % c["J"])
    if bc is None:
        stats["unsupported_operand"] = stats.get("unsupported_operand", 0) + 1
        return False
    ins, fa, fb, ty = bc
    tag = mod.tag(c["J"])
    cname = "%%p1_%x_c%x" % (A, c["J"])
    ins.append("  %s = fcmp %s %s %s, %s%s" % (cname, pred, ty, fa, fb, tag))
    use = cname
    if o == "neg":
        ins.append("  %s_n = xor i1 %s, true%s" % (cname, cname, tag))
        use = cname + "_n"
    new_br = re.sub(r"^(\s*br i1 )\S+,", lambda m: m.group(1) + use + ",", ln, count=1)
    fn.blocks[bi].lines[li] = new_br
    fn.blocks[bi].lines[li:li] = ins
    stats["rewired"] = stats.get("rewired", 0) + 1
    return True


# =====================================================================================
# dropped / folded 分岐の再構成 (mini-lifter)
# =====================================================================================

class Unsupported(Exception):
    pass


_MOV_RR = {"movaps", "movapd", "movdqa", "movups", "movupd", "movdqu", "vmovaps", "vmovapd", "vmovdqa"}
_ZERO_X = {"xorps", "xorpd", "pxor", "vxorps", "vxorpd", "vpxor"}


def _reg_ops(it):
    from ..mc import _canon_reg
    out = []
    for o in it.ops:
        if o.type == 1:
            out.append(("reg", _canon_reg(it._ci, o.reg)))
        elif o.type == 2:
            out.append(("imm", o.imm))
        else:
            out.append(("mem", None))
    return out


class Region:
    """脱落側断片を IR 化する (木構造の断片のみ; 合流は既存ブロックへの辺だけ許す)。

    語彙 (CAB-239 拡張):
      - GPR mov/imm/movabs, GPR load/store, GPR ALU (or/and/xor/add/sub/inc/dec)
      - rsp 基準 spill slot (RetDec と同じ movsd store-form/load-form の SSA 流し)
      - 断片内 call (declare 駆動。第5引数以降は call site の [rsp+0x20+8i] スロット)
      - 整数フラグ分岐 (cmp/test + jcc/setcc), rcr (comis/cmp の CF で回転)
      - movd/movq による xmm→GPR 抽出
    状態は st 辞書で運ぶ: "__w"=書込 reg, "rsp"={off: (val,ty)}, "fl"=flag 状態。
    """

    def __init__(self, mod, fn, mf, binder, rec, S, D):
        self.mod, self.fn, self.mf, self.b = mod, fn, mf, binder
        self.rec, self.S, self.D = rec, S, D
        self.blocks = []           # [(label, [lines])]
        self.cnt = 0
        self.leaders = set(mf.cfg().keys())
        self.vocab = {}            # 語彙ごとの使用数 (stats 記録用)
        self.rsp_allocas = {}      # rsp disp → alloca 名 (head block に後で挿入)
        self.rsp_alloca_lines = []

    def nm(self, va, tag):
        self.cnt += 1
        return "%%p1r_%x_%s%d" % (va, tag, self.cnt)

    def lab(self, va):
        return "dec_label_pc_%x" % va

    def used(self, key):
        self.vocab[key] = self.vocab.get(key, 0) + 1

    def read_reg(self, st, reg, va, out):
        if reg in st:
            return st[reg]
        v = self.b.bind(reg, va)
        if v is None:
            raise Unsupported("bind %s @%x" % (reg, va))
        if isinstance(v[0], str) and v[0].startswith("@@load:"):
            a = v[0][7:]
            n = self.nm(va, "ld")
            out.append("  %s = load %s, ptr %s%s" % (n, v[1], a, self.mod.tag(va)))
            v = (n, v[1])
        st[reg] = v
        return v

    def global_ref(self, va_abs, size):
        gname = "@global_var_%x" % va_abs
        ty = {16: "i128", 8: "i64", 4: "i32"}.get(size)
        if ty is None:
            raise Unsupported("mem size %s" % size)
        have = [it for it in self.mod.items if isinstance(it, str) and it.startswith(gname + " = ")]
        if have:
            m = re.search(r"(?:constant|global) (i\d+)\b", have[0])
            if m:
                # 既存定義の型を優先 (幅違いは load 側で trunc/bitcast する) — CAB-239
                return gname, m.group(1)
            m2 = re.search(r"\[(\d+) x (i\d+)\]", have[0])
            if m2:
                return gname, m2.group(2)
        else:
            self.mod.add_global("%s = external local_unnamed_addr constant %s" % (gname, ty))
        return gname, ty

    # ---- 拡張語彙: GPR mov / メモリ load/store / SSE 算術 (正規名 helper 呼出) ----
    _GPR_ALU = {"or": "or", "and": "and", "xor": "xor", "add": "add", "sub": "sub"}
    _ITyw = {"i64": 64, "i32": 32, "i16": 16, "i8": 8}

    def _gpr_val(self, st, reg, va, out, bits=64):
        v = self.read_reg(st, reg, va, out)
        name, ty = v
        w = {"i64": 64, "i32": 32, "i16": 16, "i8": 8}.get(ty)
        if w is None:
            raise Unsupported("gpr %s type %s" % (reg, ty))
        if w == bits:
            return name
        n = self.nm(va, "gc")
        out.append("  %s = %s %s %s to i%d" % (n, "trunc" if w > bits else "zext", ty, name, bits))
        return n

    def _addr(self, it, st, out, va, tag):
        """メモリ operand の IR ptr 値 (名前) を返す。rsp 基準は _rsp 経由で別扱い (Unsupported に落とす)。"""
        m = it.mem
        if m is None or m["seg"]:
            raise Unsupported("addr form")
        if m["base"] == "rip":
            g, gty = self.global_ref(m["rip"], m["size"] if m["size"] in (4, 8, 16) else 8)
            return g
        if m["base"] in (None, "rsp"):
            raise Unsupported("addr base %s" % m["base"])
        cur = self._gpr_val(st, m["base"], va, out)
        if m["index"]:
            ix = self._gpr_val(st, m["index"], va, out)
            n = self.nm(va, "ai")
            out.append("  %s = mul i64 %s, %d%s" % (n, ix, m["scale"], tag))
            n2 = self.nm(va, "as")
            out.append("  %s = add i64 %s, %s%s" % (n2, cur, n, tag))
            cur = n2
        if m["disp"]:
            n = self.nm(va, "ad")
            out.append("  %s = add i64 %s, %d%s" % (n, cur, m["disp"], tag))
            cur = n
        p = self.nm(va, "ap")
        out.append("  %s = inttoptr i64 %s to ptr%s" % (p, cur, tag))
        return p

    def _decl_helper(self, base, ret, args):
        """helper 宣言名を決める。既存 declare の (base, 戻り, 引数) が一致する物を
        無接尾 → .N/__N 接尾の順で再利用する (F6 [ir9] が無接尾名を基準に thread するため。
        新規は正規名 `__asm_<base>__<ret><args>`)。"""
        ct = {"x": "i128", "q": "i64", "d": "i32", "b": "i8", "v": "void"}
        want = [ct[a] for a in args]
        decls = self.mod.declares()
        cands = sorted((n for n in decls if re.match(r"__asm_%s(?:\.\d+|__\d+)?$" % re.escape(base), n)),
                       key=lambda n: (n != "__asm_" + base, n))       # 無接尾を最優先
        for n in cands:
            d_ret, d_args, _l = decls[n]
            if d_ret == ct[ret] and [a.strip().split()[0] for a in IR.split_args(d_args) if a.strip()] == want:
                return n
        nm = "__asm_%s__%s%s" % (base, ret, "".join(args))
        if nm not in decls:
            self.mod.add_declare("declare %s @%s(%s) local_unnamed_addr" % (ct[ret], nm, ", ".join(want)))
        return nm

    # ---- CAB-239 語彙: rsp slot / call / 整数フラグ / GPR 拡張 --------------------

    def _rsp(self, it, st, out, va, tag, write):
        """rsp 基準の spill slot。値は head block に作る alloca 経由で受け渡す
        (region 内の複数 block / 他 site の region でも支配関係が保たれる)。"""
        m = it.mem
        if m["base"] != "rsp" or m["index"] or m["seg"]:
            raise Unsupported("rsp slot form %s" % it.op_str)
        off = m["disp"]
        base = it.mnem.lstrip("v")
        dst = _canon_reg(it._ci, it.ops[0].reg) if it.ops and it.ops[0].type == 1 else None
        ap = self.rsp_allocas.get(off)
        if ap is None:
            ap = "%%p1r_%x_rsp%x" % (self.D, off & 0xFFFFFFFF)
            self.rsp_allocas[off] = ap
            self.rsp_alloca_lines.append("  %s = alloca i64" % ap)
        if write:
            x = self.read_reg(st, _canon_reg(it._ci, it.ops[1].reg), va, out)
            if x[1] != "i128":
                raise Unsupported("rsp store xmm type")
            n = self.nm(va, "rs")
            out.append("  %s = call i64 @%s(i128 %s)%s" % (n, self._decl_helper(base, "q", ["x"]), x[0], tag))
            out.append("  store i64 %s, ptr %s, align 4%s" % (n, ap, tag))
            self.used("rsp_store")
            return True
        # load
        if base in ("movsd", "movss") and m["size"] in (4, 8):
            ld = self.nm(va, "rl")
            n = self.nm(va, "rl2")
            out.append("  %s = load i64, ptr %s, align 4%s" % (ld, ap, tag))
            out.append("  %s = call i128 @%s(i64 %s)%s" % (n, self._decl_helper(base, "x", ["q"]), ld, tag))
            st[dst] = (n, "i128")
            st["__w"].add(dst)
            self.used("rsp_load")
            return True
        if m["size"] == 16:
            # 16B 復元 (vmovdqa xmmK, [rsp+off]) — RetDec は entry save を reg2mem 化している事が多い
            bv = self.b.bind(dst, va)
            if bv is None:
                raise Unsupported("rsp restore %s" % dst)
            if isinstance(bv[0], str) and bv[0].startswith("@@load:"):
                n = self.nm(va, "ld")
                out.append("  %s = load %s, ptr %s%s" % (n, bv[1], bv[0][7:], self.mod.tag(va)))
                bv = (n, bv[1])
            st[dst] = bv
            st["__w"].add(dst)
            self.used("rsp_restore_bind")
            return True
        raise Unsupported("rsp load %s size %d" % (base, m["size"]))

    def _lift_call(self, it, st, out, va, tag):
        """断片内 call。declare (RetDec) の引数型列を (rcx,rdx,r8,r9) に対応付け,
        第5引数以降は call site の [rsp+0x20+8i] slot (callee 側スタック引数) から。
        戻り: rax = 宣言の戻り型。xmm0 は「call 戻り値の bits」を仮置きする
        (F6/leafabi が callee を bits 戻りに差替えた経路と整合; raw では survivor 経路と同品質)。"""
        callee = "function_%x" % it.target
        decl = self.mod.declares().get(callee)
        dfn = self.mod.func(callee)
        if decl is None and dfn is not None:
            # define 済み callee: define の引数列を使う (declare 追加はしない — 再定義エラー回避)
            m = IR.DEFINE.match(dfn.sig)
            ret = m.group(1).split()[0]
            decl = (ret, ", ".join(ty for ty, _n in dfn.params()), None)
        elif decl is None:
            self.mod.add_declare("declare i64 @%s() local_unnamed_addr" % callee)
            ret, argtys = "i64", []
        else:
            ret = decl[0]
        argtys = [a.split()[0] for a in IR.split_args(decl[1]) if a.strip()] if decl else []
        gprs = ["rcx", "rdx", "r8", "r9"]
        if len(argtys) > 8:
            raise Unsupported("call args %d" % len(argtys))
        vals = []
        slots = st.get("rsp", {})
        for i, ty in enumerate(argtys):
            if ty == "ptr" or ty.startswith("i"):
                bits = {"ptr": 64}.get(ty) or self._ITyw.get(ty, 64)
                if i < 4:
                    v = self._gpr_val(st, gprs[i], va, out, bits=bits)
                else:
                    key = 0x20 + 8 * (i - 4)
                    if key not in slots:
                        raise Unsupported("call stack arg %d (slot %x 未追跡)" % (i + 1, key))
                    v = self._gpr_val_from(st, slots[key], va, out, bits=bits, tag=tag)
                if ty == "ptr":
                    p = self.nm(va, "cp")
                    out.append("  %s = inttoptr i64 %s to ptr%s" % (p, v, tag))
                    v = p
                vals.append("%s %s" % (ty, v))
            else:
                raise Unsupported("call arg type %s" % ty)
        rn = self.nm(va, "cl")
        callty = "i64" if ret not in ("void", "i64", "i32", "i8", "i16", "ptr") else ret
        if callty != ret:
            raise Unsupported("call ret type %s" % ret)
        if not vals and callty == "i64" and "xmm0" in st:
            # F6 [ir9] crt_patch が「直前 __asm_sd dest」(無接尾名) を arg として thread する。
            # region 内では直前の sd-op が別 block (text 上遠い / 他 site の物) になるため,
            # 同一 block に直前 marker を置いて thread 先を保証する
            # (movsd load-form i64→i128 は恒等変換ゆえ値は不変)。
            t64 = self.nm(va, "tt")
            mk = self.nm(va, "th")
            out.append("  %s = trunc i128 %s to i64%s" % (t64, st["xmm0"][0], tag))
            out.append("  %s = call i128 @%s(i64 %s)%s" % (mk, self._decl_helper("movsd", "x", ["q"]), t64, tag))
            self.used("call_arg_marker")
        out.append("  %s = call %s @%s(%s)%s" % (rn, callty, callee, ", ".join(vals), tag))
        for r in ("rcx", "rdx", "r8", "r9", "r10", "r11"):
            st.pop(r, None)
        st["__w"].difference_update(("rcx", "rdx", "r8", "r9", "r10", "r11"))
        st["fl"] = None                       # call で flag は破壊される
        if callty != "void":
            st["rax"] = (rn, callty if callty != "ptr" else "i64")
            st["__w"].add("rax")
            # xmm0 戻りの仮置き (bits): 実 xmm0 戻りは callee の leafabi/F6 差替後に bits として流れる
            z = self.nm(va, "cx")
            src = rn
            if callty == "ptr":
                ip = self.nm(va, "ci")
                out.append("  %s = ptrtoint ptr %s to i64%s" % (ip, rn, tag))
                src = ip
            out.append("  %s = zext i64 %s to i128%s" % (z, src, tag))
            st["xmm0"] = (z, "i128")
            st["__w"].add("xmm0")
        self.used("call")
        return True

    def _gpr_val_from(self, st, v, va, out, bits, tag):
        name, ty = v
        w = self._ITyw.get(ty, 64)
        if w == bits:
            return name
        n = self.nm(va, "gs")
        out.append("  %s = %s %s %s to i%d%s" % (n, "trunc" if w > bits else "zext", ty, name, bits, tag))
        return n

    def _site_cmp_vals(self, out):
        """site の comis (rec) から (fa, fb, ty) を用意する (build_compare を流用)。"""
        rec = self.rec
        if "cmp" not in rec:
            call_ln = rec["call"][2]
            kind = parse_comis_call(call_ln)[0]
            bc = build_compare(self.mod, rec["A"], call_ln, kind)
            if bc is None:
                raise Unsupported("comis operand form (region)")
            rec["cmp"] = bc
        _i, fa, fb, ty = rec["cmp"]
        return fa, fb, ty

    def _cmp_operands(self, fl, out, va, tag):
        """flag 状態から比較 operand (fa, fb, ty) を用意する。fl: ("site",None) | ("comis",(kind,a,bv))。"""
        kind, data = fl
        if kind == "site":
            return self._site_cmp_vals(out)
        fkind, a, bv = data
        ty, ity = ("double", "i64") if fkind == "d" else ("float", "i32")
        if a[1] != "i128":
            raise Unsupported("comis a type")
        ta, tb = self.nm(va, "ta"), self.nm(va, "tb")
        fa, fb = self.nm(va, "fa"), self.nm(va, "fb")
        out.append("  %s = trunc i128 %s to %s%s" % (ta, a[0], ity, tag))
        out.append("  %s = bitcast %s %s to %s%s" % (fa, ity, ta, ty, tag))
        if bv[1] == "i128":
            out.append("  %s = trunc i128 %s to %s%s" % (tb, bv[0], ity, tag))
            out.append("  %s = bitcast %s %s to %s%s" % (fb, ity, tb, ty, tag))
        elif bv[1] == ity:
            out.append("  %s = bitcast %s %s to %s%s" % (fb, ity, bv[0], ty, tag))
        else:
            raise Unsupported("comis b type %s" % bv[1])
        return fa, fb, ty

    def _flag_zf_i1(self, st, out, va, tag):
        """現在の flag 状態から ZF (i1) を作る (rcr は ZF を保存するため再帰)。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("flag state cleared (zf)")
        n = self.nm(va, "zf")
        if fl[0] in ("comis", "site"):
            fa, fb, ty = self._cmp_operands(fl, out, va, tag)
            out.append("  %s = fcmp ueq %s %s, %s%s" % (n, ty, fa, fb, tag))
            return n
        if fl[0] == "rcrcf":
            _cf, _bits, prev = fl[1]
            return self._flag_zf_i1({**st, "fl": prev}, out, va, tag)
        a, b, is_test, bits = fl[1]
        if is_test:
            t = self.nm(va, "ta")
            out.append("  %s = and i%d %s, %s%s" % (t, bits, a, b, tag))
            out.append("  %s = icmp eq i%d %s, 0%s" % (n, bits, t, tag))
        else:
            out.append("  %s = icmp eq i%d %s, %s%s" % (n, bits, a, b, tag))
        return n

    def _flag_cc_i1(self, st, cc, out, va, tag):
        """flag 状態 + 条件コード → i1。rcr 由来の CF/ZF 合成を含む。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("flag state cleared")
        if fl[0] != "rcrcf":
            return None                          # 通常経路 (comis/int) は各 handler で処理
        cf, bits, prev = fl[1]
        n = self.nm(va, "fc")
        if cc in ("b", "c", "nae"):
            n = cf
        elif cc in ("ae", "nb", "nc"):
            out.append("  %s = xor i1 %s, true%s" % (n, cf, tag))
        elif cc in ("e", "z"):
            n = self._flag_zf_i1(st, out, va, tag)
        elif cc in ("ne", "nz"):
            z = self._flag_zf_i1(st, out, va, tag)
            out.append("  %s = xor i1 %s, true%s" % (n, z, tag))
        elif cc in ("be", "na"):
            z = self._flag_zf_i1(st, out, va, tag)
            out.append("  %s = or i1 %s, %s%s" % (n, cf, z, tag))
        elif cc in ("a", "nbe"):
            z = self._flag_zf_i1(st, out, va, tag)
            c2 = self.nm(va, "fc2")
            out.append("  %s = xor i1 %s, true%s" % (c2, z, tag))
            out.append("  %s = and i1 %s, %s%s" % (n, cf, c2, tag))
        else:
            raise Unsupported("rcr cc %s" % cc)
        return n

    def _flag_cf_i1(self, st, out, va, tag):
        """現在の flag 状態から CF (i1) を作る。comis/site → fcmp ult / 整数 cmp → icmp ult / test → 0 / rcr → 保存 CF。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("flag state cleared")
        if fl[0] == "rcrcf":
            return fl[1][0]
        n = self.nm(va, "cf")
        if fl[0] in ("comis", "site"):
            fa, fb, ty = self._cmp_operands(fl, out, va, tag)
            out.append("  %s = fcmp ult %s %s, %s%s" % (n, ty, fa, fb, tag))
            return n
        a, b, is_test, bits = fl[1]
        if is_test:
            out.append("  %s = icmp eq i%d 0, 1%s" % (n, bits, tag))    # test の CF は 0
        else:
            out.append("  %s = icmp ult i%d %s, %s%s" % (n, bits, a, b, tag))
        return n

    def _int_jcc(self, it, st, out, va, tag):
        """整数フラグ分岐 (cmp/test + jcc) の IR 化。comis 系は fcmp へ流用。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("jcc without flag producer @%x" % va)
        cc = it.cc
        c = self._flag_cc_i1(st, cc, out, va, tag)
        if c is not None:
            lt = self.edge(it.target, st)
            lf = self.edge(it.next, st)
            out.append("  br i1 %s, label %%%s, label %%%s%s" % (c, lt, lf, tag))
            self.used("int_jcc")
            return out
        if fl[0] in ("comis", "site"):
            fa, fb, ty = self._cmp_operands(fl, out, va, tag)
            pred = CC_PRED.get(cc)
            if pred is None:
                raise Unsupported("cc %s" % cc)
            c = self.nm(va, "ic")
            out.append("  %s = fcmp %s %s %s, %s%s" % (c, pred, ty, fa, fb, tag))
        else:
            a, b, is_test, bits = fl[1]
            if is_test:
                pred = {"e": "eq", "ne": "ne"}.get(cc)
                if pred is None:
                    raise Unsupported("test cc %s" % cc)
                t = self.nm(va, "ta")
                out.append("  %s = and i%d %s, %s%s" % (t, bits, a, b, tag))
                c = self.nm(va, "ic")
                out.append("  %s = icmp %s i%d %s, 0%s" % (c, pred, bits, t, tag))
            else:
                pred = {"b": "ult", "c": "ult", "nae": "ult", "ae": "uge", "nb": "uge", "nc": "uge",
                        "e": "eq", "z": "eq", "ne": "ne", "nz": "ne", "be": "ule", "na": "ule",
                        "a": "ugt", "nbe": "ugt", "l": "slt", "nge": "slt", "ge": "sge", "nl": "sge",
                        "le": "sle", "ng": "sle", "g": "sgt", "nle": "sgt"}.get(cc)
                if pred is None:
                    raise Unsupported("int cc %s" % cc)
                c = self.nm(va, "ic")
                out.append("  %s = icmp %s i%d %s, %s%s" % (c, pred, bits, a, b, tag))
        lt = self.edge(it.target, st)
        lf = self.edge(it.next, st)
        out.append("  br i1 %s, label %%%s, label %%%s%s" % (c, lt, lf, tag))
        self.used("int_jcc")
        return out

    def _lift_setcc(self, it, st, out, va, tag):
        """setcc r8 — 整数フラグ → 0/1 を GPR に格納。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("setcc without flag producer @%x" % va)
        cc = it.mnem[3:]
        dst = _canon_reg(it._ci, it.ops[0].reg)
        c = self._flag_cc_i1(st, cc, out, va, tag)
        if c is None:
            if fl[0] in ("comis", "site"):
                fa, fb, ty = self._cmp_operands(fl, out, va, tag)
                pred = CC_PRED.get(cc)
                if pred is None:
                    raise Unsupported("cc %s" % cc)
                c = self.nm(va, "sc")
                out.append("  %s = fcmp %s %s %s, %s%s" % (c, pred, ty, fa, fb, tag))
            else:
                a, b, is_test, bits = fl[1]
                if is_test:
                    pred = {"e": "eq", "ne": "ne", "s": "slt"}.get(cc)
                    if pred is None:
                        raise Unsupported("test setcc %s" % cc)
                    t = self.nm(va, "ta")
                    out.append("  %s = and i%d %s, %s%s" % (t, bits, a, b, tag))
                    c = self.nm(va, "sc")
                    out.append("  %s = icmp %s i%d %s, 0%s" % (c, pred, bits, t, tag))
                else:
                    pred = {"b": "ult", "c": "ult", "nae": "ult", "ae": "uge", "nb": "uge", "nc": "uge",
                            "e": "eq", "ne": "ne", "be": "ule", "a": "ugt", "nbe": "ugt",
                            "l": "slt", "ge": "sge", "le": "sle", "g": "sgt"}.get(cc)
                    if pred is None:
                        raise Unsupported("int setcc %s" % cc)
                    c = self.nm(va, "sc")
                    out.append("  %s = icmp %s i%d %s, %s%s" % (c, pred, bits, a, b, tag))
        z = self.nm(va, "sz")
        out.append("  %s = zext i1 %s to i8%s" % (z, c, tag))
        st[dst] = (z, "i8")
        st["__w"].add(dst)
        self.used("setcc")
        return True

    def _lift_cmov(self, it, st, out, va, tag):
        """cmovcc r, r — フラグ条件 select。cc の意味: 条件成立で src を採用。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("cmov without flag producer @%x" % va)
        cc = it.mnem[4:]
        dst = _canon_reg(it._ci, it.ops[0].reg)
        src = _canon_reg(it._ci, it.ops[1].reg)
        bits = it._ci.operands[0].size * 8
        d = self._gpr_val(st, dst, va, out, bits=bits)
        s = self._gpr_val(st, src, va, out, bits=bits)
        c = self._flag_cc_i1(st, cc, out, va, tag)
        if c is None:
            if fl[0] in ("comis", "site"):
                fa, fb, ty = self._cmp_operands(fl, out, va, tag)
                pred = CC_PRED.get(cc)
                if pred is None:
                    raise Unsupported("cmov cc %s" % cc)
                c = self.nm(va, "mc")
                out.append("  %s = fcmp %s %s %s, %s%s" % (c, pred, ty, fa, fb, tag))
            else:
                a, b, is_test, w = fl[1]
                if is_test:
                    pred = {"e": "eq", "ne": "ne"}.get(cc)
                    if pred is None:
                        raise Unsupported("cmov test cc %s" % cc)
                    t = self.nm(va, "ta")
                    out.append("  %s = and i%d %s, %s%s" % (t, w, a, b, tag))
                    c = self.nm(va, "mc")
                    out.append("  %s = icmp %s i%d %s, 0%s" % (c, pred, w, t, tag))
                else:
                    pred = {"b": "ult", "c": "ult", "nae": "ult", "ae": "uge", "nb": "uge", "nc": "uge",
                            "e": "eq", "ne": "ne", "be": "ule", "na": "ule", "a": "ugt", "nbe": "ugt",
                            "l": "slt", "ge": "sge", "le": "sle", "g": "sgt"}.get(cc)
                    if pred is None:
                        raise Unsupported("cmov int cc %s" % cc)
                    c = self.nm(va, "mc")
                    out.append("  %s = icmp %s i%d %s, %s%s" % (c, pred, w, a, b, tag))
        ty = "i%d" % bits if bits < 64 else "i64"
        n = self.nm(va, "mv")
        out.append("  %s = select i1 %s, i%d %s, i%d %s%s" % (n, c, bits, s, bits, d, tag))
        st[dst] = (n, ty)
        st["__w"].add(dst)
        self.used("cmov")
        return True

    def lift_data_insn(self, it, ops, st, out, tag):
        from ..simd import kernels
        from ..mc import _canon_reg
        va, m = it.va, it.mnem
        mem = it.mem
        # --- CAB-239 語彙 (断片内で必要になる拡張) ---
        # rsp 基準 spill slot (xmm)
        if mem and mem["base"] == "rsp" and not mem["lea"] and not mem["index"]:
            xr0 = it.ops and it.ops[0].type == 1 and _canon_reg(it._ci, it.ops[0].reg).startswith("xmm")
            xr1 = len(it.ops) > 1 and it.ops[1].type == 1 and _canon_reg(it._ci, it.ops[1].reg).startswith("xmm")
            if (xr0 or xr1) and m.lstrip("v") in ("movsd", "movss", "movaps", "movapd", "movups", "movupd", "movdqa", "movdqu"):
                return self._rsp(it, st, out, va, tag, write=mem["write"])
        # 断片内 call
        if it.is_call and it.target is not None and not mem:
            return self._lift_call(it, st, out, va, tag)
        # setcc (整数フラグ → GPR)
        if m.startswith("set") and len(ops) == 2 and ops[0][0] == "reg" and not mem:
            return self._lift_setcc(it, st, out, va, tag)
        # cmovcc r, r/m — フラグ条件 select (comis/cmp 由来)
        if m.startswith("cmov") and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "reg" and not mem:
            return self._lift_cmov(it, st, out, va, tag)
        # cvttsd2si / cvttss2si r, xmm (kernels に (d|q, x) がある)
        if m.lstrip("v") in ("cvttsd2si", "cvttss2si", "cvtsd2si", "cvtss2si") and len(ops) == 2 \
                and ops[0][0] == "reg" and ops[1][0] == "reg" and not mem:
            bits = it._ci.operands[0].size * 8
            rt = "d" if bits <= 32 else "q"
            sp = kernels.lookup(m.lstrip("v"), rt, ["x"])
            if sp is None:
                return False
            x = self.read_reg(st, ops[1][1], va, out)
            if x[1] != "i128":
                raise Unsupported("cvt src type")
            hn = self._decl_helper(m.lstrip("v"), rt, ["x"])
            n = self.nm(va, "cv")
            ct = {"x": "i128", "q": "i64", "d": "i32"}[rt]
            out.append("  %s = call %s @%s(i128 %s)%s" % (n, ct, hn, x[0], tag))
            st[ops[0][1]] = (n, "i%d" % bits if bits < 64 else "i64")
            st["__w"].add(ops[0][1])
            self.used("cvt_int")
            return True
        # rcr/rcl r, 1 — CF (comis/cmp 由来) で回転。CF 出力 = 旧 bit0 (ZF は保存)
        if m in ("rcr", "rcl") and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "imm" and ops[1][1] == 1 and not mem:
            dst = ops[0][1]
            bits = it._ci.operands[0].size * 8
            v = self._gpr_val(st, dst, va, out, bits=bits)
            prev_fl = st.get("fl")
            cf = self._flag_cf_i1(st, out, va, tag)
            z = self.nm(va, "cz")
            sh = self.nm(va, "cs")
            r = self.nm(va, "cr")
            b0 = self.nm(va, "cb")
            cf1 = self.nm(va, "cc")
            out.append("  %s = and i%d %s, 1%s" % (b0, bits, v, tag))
            out.append("  %s = icmp ne i%d %s, 0%s" % (cf1, bits, b0, tag))
            z = self.nm(va, "cz")
            out.append("  %s = zext i1 %s to i%d%s" % (z, cf, bits, tag))
            if m == "rcr":
                top = self.nm(va, "ct")
                out.append("  %s = lshr i%d %s, 1%s" % (sh, bits, v, tag))
                out.append("  %s = shl i%d %s, %d%s" % (top, bits, z, bits - 1, tag))
                out.append("  %s = or i%d %s, %s%s" % (r, bits, sh, top, tag))
            else:
                out.append("  %s = shl i%d %s, 1%s" % (sh, bits, v, tag))
                out.append("  %s = or i%d %s, %s%s" % (r, bits, sh, z, tag))
            st[dst] = (r, "i%d" % bits if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = ("rcrcf", (cf1, bits, prev_fl))   # CF=旧bit0 / ZF=保存
            self.used("rot")
            return True
        # lea r, [m] — アドレス算術 (rip → global 実アドレス / GPR base+index+disp)
        if m == "lea" and mem and len(ops) == 2 and ops[0][0] == "reg" and not mem["seg"]:
            if mem["base"] == "rip" and not mem["index"]:
                g, _gty = self.global_ref(mem["rip"], 8)
                n = self.nm(va, "lp")
                out.append("  %s = ptrtoint ptr %s to i64%s" % (n, g, tag))
            else:
                if mem["base"] in (None, "rsp"):
                    raise Unsupported("lea base %s" % mem["base"])
                cur = self._gpr_val(st, mem["base"], va, out)
                if mem["index"]:
                    ix2 = self._gpr_val(st, mem["index"], va, out)
                    i1 = self.nm(va, "li")
                    out.append("  %s = mul i64 %s, %d%s" % (i1, ix2, mem["scale"], tag))
                    i2 = self.nm(va, "ls")
                    out.append("  %s = add i64 %s, %s%s" % (i2, cur, i1, tag))
                    cur = i2
                if mem["disp"]:
                    i3 = self.nm(va, "ld")
                    out.append("  %s = add i64 %s, %d%s" % (i3, cur, mem["disp"], tag))
                    cur = i3
                n = cur
            st[ops[0][1]] = (n, "i64")
            st["__w"].add(ops[0][1])
            self.used("lea")
            return True
        # --- GPR: mov r,r / mov r,imm / movabs r,imm / xor r,r
        if m in ("mov", "movabs") and len(ops) == 2 and ops[0][0] == "reg" and ops[0][1].startswith("r") and not mem:
            if ops[1][0] == "reg":
                st[ops[0][1]] = self.read_reg(st, ops[1][1], va, out)
            elif ops[1][0] == "imm":
                w = it._ci.operands[0].size * 8
                imm = ops[1][1]
                if w < 64:
                    imm &= (1 << w) - 1
                elif imm >= (1 << 63):
                    imm -= (1 << 64)
                st[ops[0][1]] = (str(imm), "i64" if w == 64 else "i%d" % w)
                if m == "movabs":
                    self.used("movabs")
            else:
                return False
            st["__w"].add(ops[0][1])
            return True
        if m == "xor" and len(ops) == 2 and ops[0] == ops[1] and ops[0][0] == "reg":
            st[ops[0][1]] = ("0", "i64")
            st["__w"].add(ops[0][1])
            return True
        # --- GPR load: mov r, [m]
        if m in ("mov", "movabs") and mem and mem["read"] and not mem["write"] and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "mem":
            sz = mem["size"]
            ity = {1: "i8", 2: "i16", 4: "i32", 8: "i64"}.get(sz)
            if ity is None:
                return False
            p = self._addr(it, st, out, va, tag)
            n = self.nm(va, "lg")
            out.append("  %s = load %s, ptr %s, align 1%s" % (n, ity, p, tag))
            st[ops[0][1]] = (n, ity)
            st["__w"].add(ops[0][1])
            self.used("gpr_load")
            return True        # --- GPR ALU (RMW): or/and/xor/add/sub/inc/dec r, r|imm|mem
        if (m in self._GPR_ALU or m in ("inc", "dec")) and len(ops) == 2 and ops[0][0] == "reg" \
                and ops[0][1].startswith("r") and not mem:
            dst = ops[0][1]
            if dst == "rsp":
                if m in ("add", "sub") and ops[1][0] == "imm":
                    self.used("rsp_adj")      # スタックポインタ調整は値に影響しない (slot は disp 基準)
                    return True
                raise Unsupported("rsp alu %s" % it.op_str)
            bits = it._ci.operands[0].size * 8
            a = self._gpr_val(st, dst, va, out, bits=bits)
            if ops[1][0] == "reg":
                b = self._gpr_val(st, ops[1][1], va, out, bits=bits)
            elif ops[1][0] == "mem":
                ity = {1: "i8", 2: "i16", 4: "i32", 8: "i64"}.get(mem["size"])
                if ity is None:
                    return False
                p = self._addr(it, st, out, va, tag)
                b = self.nm(va, "lm")
                out.append("  %s = load %s, ptr %s, align 1%s" % (b, ity, p, tag))
                if ity != "i%d" % bits:
                    t2 = self.nm(va, "lz")
                    out.append("  %s = zext %s %s to i%d%s" % (t2, ity, b, bits, tag))
                    b = t2
            else:
                imm = ops[1][1]
                if m in ("inc", "dec"):
                    imm = 1
                elif bits < 64:
                    imm &= (1 << bits) - 1
                elif imm >= (1 << 63):
                    imm -= (1 << 64)
                b = str(imm)
            iop = self._GPR_ALU.get(m, "add" if m == "inc" else "sub")
            n = self.nm(va, "al")
            out.append("  %s = %s i%d %s, %s%s" % (n, iop, bits, a, b, tag))
            st[dst] = (n, "i%d" % bits if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = None                    # フラグは再定義される (消費する jcc は未対応)
            self.used("gpr_alu")
            return True
        # --- shift (shr/sar/shl r, imm) — 値のみ (flag は未追跡)
        if m in ("shr", "sar", "shl") and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "imm" and not mem:
            dst = ops[0][1]
            bits = it._ci.operands[0].size * 8
            a = self._gpr_val(st, dst, va, out, bits=bits)
            iop = {"shr": "lshr", "sar": "ashr", "shl": "shl"}[m]
            n = self.nm(va, "sh")
            out.append("  %s = %s i%d %s, %d%s" % (n, iop, bits, a, ops[1][1] & (bits - 1), tag))
            st[dst] = (n, "i%d" % bits if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = None
            self.used("shift")
            return True
        # --- cmp / test (整数フラグ生成。値は flag 状態に記録)
        if m in ("cmp", "test") and len(ops) == 2 and ops[0][0] == "reg":
            bits = it._ci.operands[0].size * 8
            a = self._gpr_val(st, ops[0][1], va, out, bits=bits)
            if ops[1][0] == "reg":
                b = self._gpr_val(st, ops[1][1], va, out, bits=bits)
            else:
                imm = ops[1][1]
                if bits < 64:
                    imm &= (1 << bits) - 1
                elif imm >= (1 << 63):
                    imm -= (1 << 64)
                b = str(imm)
            st["fl"] = ("int", (a, b, m == "test", bits))
            self.used("int_flag")
            return True
        # --- movd/movq r, xmm (抽出)
        if m.lstrip("v") in ("movd", "movq") and len(ops) == 2 and ops[0][0] == "reg" \
                and ops[0][1].startswith("r") and ops[1][0] == "reg" and not mem:
            bits = it._ci.operands[0].size * 8
            x = self.read_reg(st, ops[1][1], va, out)
            if x[1] != "i128":
                raise Unsupported("extract src type")
            n = self.nm(va, "ex")
            out.append("  %s = trunc i128 %s to i%d%s" % (n, x[0], bits, tag))
            st[ops[0][1]] = (n, "i%d" % bits if bits < 64 else "i64")
            st["__w"].add(ops[0][1])
            self.used("extract")
            return True
        # --- GPR store: mov [m], r / imm
        if m == "mov" and mem and mem["write"] and len(ops) == 2 and ops[0][0] == "mem":
            sz = mem["size"]
            ity = {1: "i8", 2: "i16", 4: "i32", 8: "i64"}.get(sz)
            if ity is None:
                return False
            p = self._addr(it, st, out, va, tag)
            if ops[1][0] == "reg":
                v = self._gpr_val(st, ops[1][1], va, out, bits=sz * 8)
            elif ops[1][0] == "imm":
                v = str(ops[1][1] if ops[1][1] < (1 << 63) else ops[1][1] - (1 << 64))
                if sz == 4 and int(v) >= (1 << 31):
                    v = str(int(v) - (1 << 32))
            else:
                return False
            out.append("  store %s %s, ptr %s, align 1%s" % (ity, v, p, tag))
            return True
        # --- SSE: 移動 / 算術
        base = m
        vex = False
        if m.startswith("v") and len(m) > 2:
            base, vex = m[1:], True
        xr = lambda o: o[0] == "reg" and o[1].startswith("xmm")
        # store: movss/movsd/movaps... [m], xmm
        if mem and mem["write"] and len(ops) == 2 and ops[0][0] == "mem" and xr(ops[1]):
            sz = mem["size"]
            if base not in ("movss", "movsd", "movaps", "movapd", "movups", "movupd", "movdqa", "movdqu", "movd", "movq"):
                return False
            ity = {4: "i32", 8: "i64", 16: "i128"}.get(sz)
            if ity is None:
                return False
            p = self._addr(it, st, out, va, tag)
            x = self.read_reg(st, ops[1][1], va, out)
            if x[1] != "i128":
                raise Unsupported("xmm type")
            if ity == "i128":
                out.append("  store i128 %s, ptr %s, align 1%s" % (x[0], p, tag))
            else:
                n = self.nm(va, "st")
                out.append("  %s = trunc i128 %s to %s%s" % (n, x[0], ity, tag))
                out.append("  store %s %s, ptr %s, align 1%s" % (ity, n, p, tag))
            return True
        # xmm 書込み命令
        if not (ops and xr(ops[0])):
            return False
        dst = ops[0][1]
        # ゼロ化 (vpxor x,x,x 等) は既に処理済み _ZERO_X (vex 3-op 形のみここへ)
        if base in ("xorps", "xorpd", "pxor") and vex and len(ops) == 3 and ops[1] == ops[2] and xr(ops[1]):
            st[dst] = ("0", "i128")
            st["__w"].add(dst)
            return True
        # capstone の operand access から (read 対象) を決める
        ci = it._ci
        args, vals = [], []
        for k, o in enumerate(ci.operands):
            if k == 0:
                if o.access & 1:             # dst も read (RMW)
                    args.append("x")
                    vals.append(self.read_reg(st, dst, va, out)[0])
                continue
            kind = ops[k][0]
            if kind == "reg":
                if not xr(ops[k]):
                    # GPR 源 (cvtsi2sd 等)
                    gv = self._gpr_val(st, ops[k][1], va, out, bits=o.size * 8)
                    args.append({4: "d", 8: "q"}.get(o.size, "q"))
                    vals.append(gv)
                else:
                    args.append("x")
                    vals.append(self.read_reg(st, ops[k][1], va, out)[0])
            elif kind == "mem":
                sz = mem["size"]
                ity = {4: "i32", 8: "i64", 16: "i128"}.get(sz)
                if ity is None:
                    return False
                p = self._addr(it, st, out, va, tag)
                n = self.nm(va, "ld")
                out.append("  %s = load %s, ptr %s, align 1%s" % (n, ity, p, tag))
                args.append({"i32": "d", "i64": "q", "i128": "x"}[ity])
                vals.append(n)
            elif kind == "imm":
                args.append("b")
                vals.append(str(ops[k][1] & 0xFF))
        # 完全上書きの移動 (movaps x,[m] / movaps x,x)
        if base in ("movaps", "movapd", "movups", "movupd", "movdqa", "movdqu") and args == ["x"]:
            st[dst] = (vals[0], "i128")
            st["__w"].add(dst)
            return True
        sp = kernels.lookup(base if not vex else m, "x", args) or kernels.lookup(m, "x", args)
        if sp is None:
            raise Unsupported("%x: no helper for %s(%s)" % (va, m, ",".join(args)))
        hn = self._decl_helper(m if (kernels.lookup(m, "x", args) is not None and vex) else base, "x", args)
        n = self.nm(va, "h")
        ct = {"x": "i128", "q": "i64", "d": "i32", "b": "i8"}
        out.append("  %s = call i128 @%s(%s)%s" % (n, hn, ", ".join("%s %s" % (ct[a], v) for a, v in zip(args, vals)), tag))
        st[dst] = (n, "i128")
        st["__w"].add(dst)
        return True

    def lift_block(self, start, st):
        """機械語 start から基本ブロック終端まで lift し IR 行を返す。
        st: "__w"=書込 reg, "rsp"=rsp slot 値, "fl"=flag 状態 (comis/整数 cmp)。"""
        mf, mod = self.mf, self.mod
        out = []
        va = start
        while True:
            it = mf.insns[va]
            tag = mod.tag(va)
            ops = _reg_ops(it)
            m = it.mnem
            if m in _MOV_RR and ops[0][0] == "reg" and ops[1][0] == "reg":
                st[ops[0][1]] = self.read_reg(st, ops[1][1], va, out)
                st["__w"].add(ops[0][1])
            elif m in _ZERO_X and len(ops) == 2 and ops[0] == ops[1] and ops[0][0] == "reg":
                st[ops[0][1]] = ("0", "i128")
                st["__w"].add(ops[0][1])
            elif m.lstrip("v") in ("comisd", "comiss", "ucomisd", "ucomiss"):
                kind = m[-1]
                a = self.read_reg(st, ops[0][1], va, out)
                if ops[1][0] == "reg":
                    bv = self.read_reg(st, ops[1][1], va, out)
                else:
                    mem = it.mem
                    if not mem or mem["rip"] is None:
                        raise Unsupported("comis mem operand %s" % it.op_str)
                    g, gty = self.global_ref(mem["rip"], mem["size"])
                    n = self.nm(va, "g")
                    out.append("  %s = load %s, ptr %s, align 8%s" % (n, gty, g, tag))
                    bv = (n, gty)
                st["fl"] = ("comis", (kind, a, bv))
                self.used("comis_frag")
            elif it.is_jcc:
                fl = st.get("fl")
                if fl is None:
                    raise Unsupported("jcc without comis @%x" % va)
                if fl[0] == "comis":
                    kind, a, bv = fl[1]
                    pred = CC_PRED.get(it.cc)
                    if pred is None:
                        raise Unsupported("cc %s" % it.cc)
                    ty, ity = ("double", "i64") if kind == "d" else ("float", "i32")
                    ta, tb = self.nm(va, "ta"), self.nm(va, "tb")
                    fa, fb = self.nm(va, "fa"), self.nm(va, "fb")
                    if a[1] != "i128":
                        raise Unsupported("comis a type")
                    out.append("  %s = trunc i128 %s to %s%s" % (ta, a[0], ity, tag))
                    out.append("  %s = bitcast %s %s to %s%s" % (fa, ity, ta, ty, tag))
                    if bv[1] == "i128":
                        out.append("  %s = trunc i128 %s to %s%s" % (tb, bv[0], ity, tag))
                        out.append("  %s = bitcast %s %s to %s%s" % (fb, ity, tb, ty, tag))
                    elif bv[1] == ity:
                        out.append("  %s = bitcast %s %s to %s%s" % (fb, ity, bv[0], ty, tag))
                    else:
                        raise Unsupported("comis b type %s" % bv[1])
                    c = self.nm(va, "c")
                    out.append("  %s = fcmp %s %s %s, %s%s" % (c, pred, ty, fa, fb, tag))
                    lt = self.edge(it.target, st)
                    lf = self.edge(it.next, st)
                    out.append("  br i1 %s, label %%%s, label %%%s%s" % (c, lt, lf, tag))
                    return out
                self._int_jcc(it, st, out, va, tag)
                return out
            elif it.is_ret:
                # 断片内 ret: rax は追跡値 (無ければ 0)。実値は xmm0 戻り (leafabi が搬送)
                rax = st.get("rax")
                rv = rax[0] if rax else "0"
                ty = rax[1] if rax else "i64"
                if ty != "i64":
                    n = self.nm(va, "rr")
                    out.append("  %s = zext %s %s to i64%s" % (n, ty, rv, tag))
                    rv = n
                out.append("  ret i64 %s%s" % (rv, tag))
                self.used("ret")
                return out
            elif m == "jmp" and it.target is not None:
                lt = self.edge(it.target, st)
                out.append("  br label %%%s%s" % (lt, tag))
                return out
            elif m.startswith("nop"):
                pass
            elif self.lift_data_insn(it, ops, st, out, tag):
                pass
            else:
                raise Unsupported("%x: %s %s" % (va, m, it.op_str))
            va = it.next
            if va in self.leaders:
                lt = self.edge(va, st)
                out.append("  br label %%%s" % lt)
                return out

    def edge(self, va, st):
        """辺 -> 先のラベル名。region 内なら再帰 lift, 既存 IR なら merge store を持つ中継ブロックを作る。"""
        if va == self.S and not self.S_is_label:
            bad = (st["__w"] - {"flags"}) & self.live_at_S
            if bad:
                raise Unsupported("region writes %s live into survivor" % sorted(bad))
            return "dec_label_pc_%x" % va
        if va in self.exit_vas:
            relay = "dec_label_pc_p1relay_%x_%d" % (self.D, len(self.blocks))
            pre = []
            self.emit_merge_stores(va, st, pre)
            self.blocks.append((relay, pre + ["  br label %%dec_label_pc_%x" % va]))
            return relay
        if va in self.visited:
            raise Unsupported("region join @%x" % va)
        if va not in self.mf.insns:
            raise Unsupported("edge outside function @%x" % va)
        self.visited.add(va)
        lab = self.lab(va)
        sub = self.lift_block(va, {k: (set(v) if k == "__w" else (dict(v) if k == "rsp" else v)) for k, v in st.items()})
        self.blocks.append((lab, sub))
        return lab

    def emit_merge_stores(self, L, st, out):
        """既存ブロック L の先頭で load される reg2mem alloca へ, この辺の値を store する。"""
        fn, ix = self.fn, self.ix
        bi = ix.label_idx.get("dec_label_pc_%x" % L)
        if bi is None:
            raise Unsupported("exit label %x" % L)
        for ln in fn.blocks[bi].lines:
            mm = re.match(r"^\s*%[\w$.\-]+ = load (\S+), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
            if not mm:
                continue
            ty, a = mm.group(1).rstrip(","), mm.group(2)
            if not a.endswith(".reg2mem"):
                continue
            rm = re.match(r"^%(r[a-z0-9]+|xmm\d+)\.\d+(?:\.in)?\.reg2mem$", a)
            val = None
            if rm and rm.group(1) in st["__w"]:
                v = st[rm.group(1)]
                if v[1] != ty and v[0] != "0":
                    raise Unsupported("alloca %s type %s vs %s" % (a, ty, v[1]))
                val = v[0]
            else:
                val = self.carry_value(a)
            if val is None:
                raise Unsupported("no value for %s" % a)
            out.append("  store %s %s, ptr %s" % (ty, val, a))

    def carry_value(self, a):
        """生存側経路が alloca a に store している値 (分岐点より前で定義済) を流用。"""
        ix = self.ix
        for (bi, li, vtok, vty) in ix.stores.get(a, []):
            if (bi, li) not in self.tail_range:
                continue
            if vtok.startswith("%"):
                d = ix.defs.get(vtok)
                if d is not None:
                    dbi, dli = d
                    if (dbi, dli) in self.tail_range:
                        continue
                    if dbi != self.head_bi and not ix.dominates(dbi, self.head_bi):
                        continue
            return vtok
        return None


def reconstruct(mod, fn, mf, binder, rec, c, stats, log):
    """脱落 (または br label に畳まれた) jcc を再構成。成功 True。失敗は Unsupported (IR 無改変)。"""
    ix = binder.ix
    A, J = rec["A"], c["J"]
    T, F = c["T"], c["F"]
    cb, cl, call_ln = rec["call"]
    blk = fn.blocks[cb]
    pT, pF = ix.present(T), ix.present(F)
    pred = CC_PRED.get(c["cc"])
    if pred is None:
        raise Unsupported("cc %s" % c["cc"])
    kind = parse_comis_call(call_ln)[0]

    # ---- head / tail の分割点: comis 呼出の後で J より後ろのアドレスを持つ最初の行。無ければ終端命令。
    sp = None
    for i in range(cl + 1, len(blk.lines)):
        a = mod.addr_of(blk.lines[i])
        if a is not None and a > J:
            sp = i
            break
    term_idx = None
    for i in range(len(blk.lines) - 1, cl, -1):
        if re.match(r"^\s*(br|ret|switch|unreachable)\b", IR.strip_tokens(blk.lines[i])):
            term_idx = i
            break
    if term_idx is None:
        raise Unsupported("no terminator in comis block")
    if sp is None:
        sp = term_idx
    tail_lines = blk.lines[sp:]

    # ---- 生存側 S: 既存 IR の到達で決める
    S = None
    if c["state"] == "folded":
        m = re.match(r"^\s*br label %([\w$.\-]+)", IR.strip_tokens(c["br"][2]))
        S = label_target(m.group(1)) if m else None
    if S is None:
        # tail の終端 `br label %L` の先, または tail 先頭の注釈アドレスで判定
        tm = re.match(r"^\s*br label %([\w$.\-]+)", IR.strip_tokens(blk.lines[term_idx]))
        t_first = None
        for ln in tail_lines:
            a = mod.addr_of(ln)
            if a is not None:
                t_first = a
                break
        if t_first is not None and (t_first == T or t_first == F or (J < t_first)):
            # 注釈付きの続きがある: T 側/F 側のどちらの領域か (機械語の fallthrough = F 側は J の直後)
            if t_first == T or (t_first > J and t_first != F and T > J and t_first >= T):
                S = T
            else:
                S = F if t_first >= F else None
        if S is None and tm:
            lt = label_target(tm.group(1))
            if lt in (T, F):
                S = lt
        if S is None:
            if pT and not pF:
                S = T
            elif pF and not pT:
                S = F
    if S not in (T, F):
        raise Unsupported("survivor ambiguous (T present=%s F present=%s)" % (pT, pF))
    D = F if S == T else T

    # ---- 機械語 CFG から region の端点 (既存 IR 側ラベル) を決める
    reg = Region(mod, fn, mf, binder, rec, S, D)
    reg.ix = ix
    reg.exit_vas = set()
    for lab, bi in ix.label_idx.items():
        mm = re.match(r"dec_label_pc_([0-9a-f]+)$", lab or "")
        if mm:
            reg.exit_vas.add(int(mm.group(1), 16))
    reg.S_is_label = ix.has_label(S)
    if not reg.S_is_label:
        reg.exit_vas.discard(S)
    reg.live_at_S = _live_in_at(mf, S)
    reg.visited = set()
    reg.head_bi = cb
    reg.tail_range = set((cb, i) for i in range(sp, len(blk.lines)))
    # tail の新ラベル (S が既存ラベルならラベル衝突を避ける)
    if reg.S_is_label:
        tail_label = "dec_label_pc_p1tail_%x_%x" % (A, J)
    else:
        tail_label = "dec_label_pc_%x" % S
    st0 = {"__w": set(), "fl": ("site", None), "rsp": {}}
    dlabel = reg.edge(D, st0)
    # ---- 比較命令 (comis 呼出直後) + 分岐
    tag = mod.tag(J)
    if "cmp" in rec:
        _i, fa, fb, ty = rec["cmp"]
        ins = [] if rec.get("cmp_ins") else list(rec["cmp"][0])
        if ins:
            rec["cmp_ins"] = True
    else:
        bc = build_compare(mod, A, call_ln, kind)
        if bc is None:
            raise Unsupported("comis operand form")
        rec["cmp"] = bc
        already = any(re.search(r"%%p1_%x_ta = " % A, IR.strip_tokens(l)) for l in blk.lines)
        if already:
            ins = []
            _i, fa, fb, ty = bc
            rec["cmp_ins"] = True
        else:
            ins, fa, fb, ty = bc
            ins = list(ins)
            rec["cmp_ins"] = True
    cname = "%%p1_%x_c%x" % (A, J)
    ins.append("  %s = fcmp %s %s %s, %s%s" % (cname, pred, ty, fa, fb, tag))
    if S == T:
        newbr = "  br i1 %s, label %%%s, label %%%s%s" % (cname, tail_label, dlabel, tag)
    else:
        newbr = "  br i1 %s, label %%%s, label %%%s%s" % (cname, dlabel, tail_label, tag)
    blk.lines[sp:] = []
    blk.lines[cl + 1:cl + 1] = ins
    blk.lines.append(newbr)
    if reg.rsp_alloca_lines:
        blk.lines[cl + 1:cl + 1] = reg.rsp_alloca_lines
    tb = IR.Block(tail_label, tail_label + ":", tail_lines)
    fn.blocks.insert(cb + 1, tb)
    for (lab, lines) in reg.blocks:
        fn.blocks.append(IR.Block(lab, lab + ":", lines))
    stats["reconstructed"] = stats.get("reconstructed", 0) + 1
    for k, v in reg.vocab.items():
        stats["vocab_" + k] = stats.get("vocab_" + k, 0) + v
    log.append("reconstructed jcc@%x (survivor=%s %x, region blocks=%d)%s" % (
        J, "T" if S == T else "F", S, len(reg.blocks),
        (" vocab=" + ",".join("%s:%d" % kv for kv in sorted(reg.vocab.items()))) if reg.vocab else ""))
    return True


def _live_in_at(mf, va):
    """機械語 va (ブロック先頭) での live-in (xmm/gpr)。"""
    blocks = mf.cfg()
    use, defn = {}, {}
    for l, b in blocks.items():
        u, d = set(), set()
        for v in b["vas"]:
            it = mf.insns[v]
            u |= (it.reads - d)
            d |= it.writes
        use[l], defn[l] = u, d
    LIVE = {l: set() for l in blocks}
    ch = True
    while ch:
        ch = False
        for l, b in blocks.items():
            out = set()
            for s in b["succ"]:
                out |= LIVE[s]
            new = use[l] | (out - defn[l])
            if new != LIVE[l]:
                LIVE[l] = new
                ch = True
    blk = mf.block_of(va)
    if blk == va:
        return LIVE[va] - {"flags"}
    # ブロック途中: そこから先の読取を後ろ向きに計算
    vas = blocks[blk]["vas"]
    idx = vas.index(va)
    live = set()
    for s in blocks[blk]["succ"]:
        live |= LIVE[s]
    for v in reversed(vas[idx:]):
        it = mf.insns[v]
        live = (live - it.writes) | it.reads
    return live - {"flags"}


def run_function(mod, fn, img, repair=True, log=None, stats=None, mf=None):
    stats = stats if stats is not None else {}
    log = log if log is not None else []
    va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
    if va is None:
        return stats
    rng = img.func_at(va)
    if rng is None:
        stats["no_pdata"] = stats.get("no_pdata", 0) + 1
        return stats
    mf = mf or MFunc(img, *rng)
    # 1 サイトずつ処理 (FuncIndex は構造変更後に作り直す)
    done = set()
    while True:
        binder = Binder(mod, fn, mf)
        sites = analyze(mod, fn, mf, binder)
        todo = None
        for rec in sites:
            if rec["call"] is None:
                continue                       # IR に無い (脱落断片内) comis は region 側が処理
            for c in rec["consumers"]:
                if (rec["A"], c["J"]) in done:
                    continue
                todo = (rec, c)
                break
            if todo:
                break
        if not todo:
            break
        rec, c = todo
        done.add((rec["A"], c["J"]))
        stats["sites"] = stats.get("sites", 0) + 1
        st = c["state"]
        stats["state_" + st] = stats.get("state_" + st, 0) + 1
        if not repair or st == "region_done":
            continue
        try:
            if st == "branch":
                if not rewire(mod, fn, binder, rec, c, stats, None):
                    log.append("rewire failed jcc@%x" % c["J"])
            elif st in ("dropped", "folded"):
                reconstruct(mod, fn, mf, binder, rec, c, stats, log)
            else:
                stats["unsupported_consumer"] = stats.get("unsupported_consumer", 0) + 1
                log.append("unsupported consumer %s@%x" % (c["mnem"], c["J"]))
        except Unsupported as e:
            stats["unsupported"] = stats.get("unsupported", 0) + 1
            log.append("UNSUPPORTED %s@%x: %s" % (st, c["J"], e))
    return stats
