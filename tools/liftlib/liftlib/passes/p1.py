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
from ..mc import MFunc
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

COMIS_CALL = re.compile(r"call void @(__asm_v?u?comis([sd])(?:__\d+|\.\d+)?)\((.*)\)")


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


def build_compare(mod, A, call_line, kind):
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
    ins.append("  %%p1_%x_ta = trunc i128 %s to %s%s" % (A, t1[1], ity, tag))
    ins.append("  %%p1_%x_fa = bitcast %s %%p1_%x_ta to %s%s" % (A, ity, A, ty, tag))
    t2 = a2.split(None, 1)
    if t2[0] == "i128":
        ins.append("  %%p1_%x_tb = trunc i128 %s to %s%s" % (A, t2[1], ity, tag))
        ins.append("  %%p1_%x_fb = bitcast %s %%p1_%x_tb to %s%s" % (A, ity, A, ty, tag))
    elif t2[0] == ity:
        ins.append("  %%p1_%x_fb = bitcast %s %s to %s%s" % (A, ity, t2[1], ty, tag))
    elif t2[0] in ("i64", "i32"):
        # 幅違い (ss なのに i64 等): trunc/bitcast
        if t2[0] == "i64" and ity == "i32":
            ins.append("  %%p1_%x_tb = trunc i64 %s to i32%s" % (A, t2[1], tag))
            ins.append("  %%p1_%x_fb = bitcast i32 %%p1_%x_tb to %s%s" % (A, A, ty, tag))
        else:
            return None
    else:
        return None
    return ins, "%%p1_%x_fa" % A, "%%p1_%x_fb" % A, ty


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
    if "cmp" not in rec:
        bc = build_compare(mod, A, call_ln, kind)
        if bc is None:
            stats["unsupported_operand"] = stats.get("unsupported_operand", 0) + 1
            return False
        rec["cmp"] = bc
        ins = list(bc[0])
    else:
        ins = []
    _i, fa, fb, ty = rec["cmp"]
    tag = mod.tag(c["J"])
    cname = "%%p1_%x_c%x" % (A, c["J"])
    ins.append("  %s = fcmp %s %s %s, %s%s" % (cname, pred, ty, fa, fb, tag))
    use = cname
    if o == "neg":
        ins.append("  %s_n = xor i1 %s, true%s" % (cname, cname, tag))
        use = cname + "_n"
    # 1 度だけ insert: comis 呼出の直後 (call は br と同ブロックか支配する)
    blk = fn.blocks[cb]
    new_br = re.sub(r"^(\s*br i1 )\S+,", lambda m: m.group(1) + use + ",", ln, count=1)
    # 注: br 行は別ブロックにあり得るので, 先に br を置換してから call の直後へ挿入
    fn.blocks[bi].lines[li] = new_br
    blk.lines[cl + 1:cl + 1] = ins
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
    """脱落側断片を IR 化する (木構造の断片のみ; 合流は既存ブロックへの辺だけ許す)。"""

    def __init__(self, mod, fn, mf, binder, rec, S, D):
        self.mod, self.fn, self.mf, self.b = mod, fn, mf, binder
        self.rec, self.S, self.D = rec, S, D
        self.blocks = []           # [(label, [lines])]
        self.cnt = 0
        self.leaders = set(mf.cfg().keys())

    def nm(self, va, tag):
        self.cnt += 1
        return "%%p1r_%x_%s%d" % (va, tag, self.cnt)

    def lab(self, va):
        return "dec_label_pc_%x" % va

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
            if m and m.group(1) != ty:
                raise Unsupported("global type %s != %s" % (m.group(1), ty))
        else:
            self.mod.add_global("%s = external local_unnamed_addr constant %s" % (gname, ty))
        return gname, ty

    def lift_block(self, start, st):
        """機械語 start から基本ブロック終端まで lift し IR 行を返す。st['__w'] = 書込済 reg 集合。"""
        mf, mod = self.mf, self.mod
        out = []
        cmp = None
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
                cmp = (kind, a, bv, va)
            elif it.is_jcc:
                if cmp is None:
                    raise Unsupported("jcc without comis @%x" % va)
                pred = CC_PRED.get(it.cc)
                if pred is None:
                    raise Unsupported("cc %s" % it.cc)
                kind, a, bv, cva = cmp
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
            elif m == "jmp" and it.target is not None:
                lt = self.edge(it.target, st)
                out.append("  br label %%%s%s" % (lt, tag))
                return out
            elif m.startswith("nop"):
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
        if va == self.S:
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
        sub = self.lift_block(va, {k: (set(v) if k == "__w" else v) for k, v in st.items()})
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
    """脱落 (または br label に畳まれた) jcc を再構成。成功 True。"""
    ix = binder.ix
    A, J = rec["A"], c["J"]
    T, F = c["T"], c["F"]
    cb, cl, call_ln = rec["call"]
    pT, pF = ix.present(T), ix.present(F)
    folded_br = c.get("br") if c["state"] == "folded" else None
    if folded_br:
        s = IR.strip_tokens(folded_br[2])
        m = re.match(r"^\s*br label %([\w$.\-]+)", s)
        S = label_target(m.group(1))
        if S not in (T, F):
            raise Unsupported("folded br target %x not in {T,F}" % (S or 0))
    elif pT and not pF:
        S = T
    elif pF and not pT:
        S = F
    else:
        raise Unsupported("survivor ambiguous (T present=%s F present=%s)" % (pT, pF))
    D = F if S == T else T
    pred = CC_PRED.get(c["cc"])
    if pred is None:
        raise Unsupported("cc %s" % c["cc"])
    kind = parse_comis_call(call_ln)[0]

    # ---- 機械語 CFG から region の端点 (既存 IR 側ラベル) を決める
    reg = Region(mod, fn, mf, binder, rec, S, D)
    reg.ix = ix
    reg.exit_vas = set()
    for lab, bi in ix.label_idx.items():
        mm = re.match(r"dec_label_pc_([0-9a-f]+)$", lab or "")
        if mm:
            reg.exit_vas.add(int(mm.group(1), 16))
    reg.exit_vas.discard(S)
    reg.live_at_S = _live_in_at(mf, S)
    reg.visited = set()

    # ---- head / tail 分割
    head_bi = cb
    blk = fn.blocks[head_bi]
    reg.head_bi = head_bi
    if folded_br:
        sp = None
        reg.tail_range = set()
        tail_label = "dec_label_pc_%x" % S
    else:
        sp = None
        for i in range(cl + 1, len(blk.lines)):
            a = mod.addr_of(blk.lines[i])
            if a is not None and a > J:
                sp = i
                break
        if sp is None:
            raise Unsupported("no split point after comis")
        tail_label = "dec_label_pc_%x" % S
        if ix.has_label(S):
            raise Unsupported("survivor label already exists but br missing")
        reg.tail_range = set((head_bi, i) for i in range(sp, len(blk.lines)))

    st0 = {"__w": set()}
    dlabel = reg.edge(D, st0)
    # ---- 比較命令 (comis 呼出直後) + 分岐
    tag = mod.tag(J)
    bc = build_compare(mod, A, call_ln, kind) if "cmp" not in rec else None
    if "cmp" in rec:
        _i, fa, fb, ty = rec["cmp"]
        ins = []
    else:
        if bc is None:
            raise Unsupported("comis operand form")
        rec["cmp"] = bc
        ins, fa, fb, ty = bc
        ins = list(ins)
    cname = "%%p1_%x_c%x" % (A, J)
    ins.append("  %s = fcmp %s %s %s, %s%s" % (cname, pred, ty, fa, fb, tag))
    if S == T:
        newbr = "  br i1 %s, label %%%s, label %%%s%s" % (cname, tail_label, dlabel, tag)
    else:
        newbr = "  br i1 %s, label %%%s, label %%%s%s" % (cname, dlabel, tail_label, tag)

    if folded_br:
        bi, li, _ = folded_br
        fn.blocks[bi].lines[li] = newbr
        fn.blocks[cb].lines[cl + 1:cl + 1] = ins
    else:
        tail_lines = blk.lines[sp:]
        blk.lines[sp:] = []
        blk.lines[cl + 1:cl + 1] = ins
        blk.lines.append(newbr)
        tb = IR.Block(tail_label, tail_label + ":", tail_lines)
        fn.blocks.insert(head_bi + 1, tb)
    for (lab, lines) in reg.blocks:
        fn.blocks.append(IR.Block(lab, lab + ":", lines))
    stats["reconstructed"] = stats.get("reconstructed", 0) + 1
    log.append("reconstructed jcc@%x (survivor=%s %x, region blocks=%d)" % (J, "T" if S == T else "F", S, len(reg.blocks)))
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
        if not repair:
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
