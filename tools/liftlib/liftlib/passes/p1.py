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
import os
import re

from .. import ir as IR
from ..mc import MFunc, _canon_reg, leaf_ext
from ..regbind import Binder, FuncIndex, TYPE_BITS, result_type

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


# p1 が領域 block を新設した機械語 VA (run_function 単位)。後続 site はこれらの VA を
# 「未 lift」扱いで自分の経路値で再 lift する (領域 block は経路固有の SSA を持つため,
# 他経路の辺 (relay 等) が直接飛び込むと支配が壊れる — LIFTLIB-2)
_REGION_VAS: set[int] = set()

# p1 が領域内で生成した値の名前: %p1r_<機械語va>_<salt>_<tag><n>
# (salt = "<A>_<J>" = site 識別子で自体内に "_" を含む。他 site の領域値の流入検出に使う — LIFTLIB-2)
P1R_NAME = re.compile(r"%p1r_([0-9a-f]+)_(.+)_")


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
    """脱落側断片を IR 化する。

    CAB-239 までは木構造の断片 (各合流点を高々 1 辺) に限っていた。LIFTLIB-2 では
    領域内合流 (DAG) を reg2mem 合成で許す — RetDec 自身と同じイディオム:
      - collect(): D から機械語 CFG を DFS し領域 block 集合を求める
        (既存 IR ラベル = 出口 (relay), S = 生存側尾部。back edge = ループは unsupported)
      - 各 block はトポロジ順に 1 度だけ lift する。合流点では pred 間で値が
        不一致の reg を「関数入口 alloca への各 pred 終端 store + 合流 block 先頭 load」
        で合成する (phi の代わり)。alloca を関数入口に置くのは, 後続 site の relay が
        合流 block へ新たな pred を足しても支配が保たれるため (RetDec の reg2mem と同じ)。
      - bind 失敗時は def 側から値を復元する: cmov (RetDec が分岐化して IR に無い)
        は直前 comis から fcmp + select で合成, 多定義は各 def を
        (IR 値 / 定数合成 / def 命令 1 個の lift) で復元し全一致の時だけ採用する。

    語彙 (CAB-239 拡張):
      - GPR mov/imm/movabs, GPR load/store, GPR ALU (or/and/xor/add/sub/inc/dec)
      - rsp 基準 spill slot (RetDec と同じ movsd store-form/load-form の SSA 流し)
      - 断片内 call (declare 駆動。第5引数以降は call site の [rsp+0x20+8i] スロット)
      - 整数フラグ分岐 (cmp/test + jcc/setcc), rcr (comis/cmp の CF で回転)
      - movd/movq による xmm→GPR 抽出
    状態は st 辞書で運ぶ: "__w"=書込 reg, "rsp"={off: (val,ty)}, "fl"=flag 状態。
    """

    def __init__(self, mod, fn, mf, binder, rec, S, D, J):
        self.mod, self.fn, self.mf, self.b = mod, fn, mf, binder
        self.rec, self.S, self.D = rec, S, D
        self.J = J                    # jcc の VA (分岐点 = 脱落側経路の bind 基準)
        self.salt = "%x_%x" % (rec["A"], J)     # site 固有の名前 salt (A, J)
        self.blocks = []           # [(label, [lines])]
        self.cnt = 0
        self.leaders = set(mf.cfg().keys())
        self.vocab = {}            # 語彙ごとの使用数 (stats 記録用)
        self.rsp_allocas = {}      # rsp disp → alloca 名 (head block に後で挿入)
        self.rsp_alloca_lines = []
        # LIFTLIB-2: 領域内合流 (DAG) の reg2mem 合成
        self.join_allocas = {}     # (join_va, reg) -> alloca 名
        self.join_alloca_lines = []  # 関数入口へ搬入 (alloca + 0 初期化)
        self.join_stores = {}      # block_va -> [行] (終端前に差し込む 変換/store/束縛)
        self.bodies = {}           # block_va -> 本体行
        self.terms = {}            # block_va -> 終端行
        self.out_states = {}       # block_va -> 終端時の st
        self.relay_n = 0
        self._resolving = set()    # bind 値合成の再帰ガード
        self._blk_live = None      # block 開始点 live-in の cache
        self._domreg = None
        self._domfull = None        # 自領域の機械語 block 支配関係 (cache)
        self.vdb = {}               # 領域値 SSA 名 -> 定義した機械語 block VA (LIFTLIB-4)
        self.vdbld = {}             # 領域値 SSA 名 -> (alloca, ty) (reissue した load のみ)
        self.cur_va = None         # 現在 lift 中の機械語 block 先頭
        self.tail_lines = []       # 生存側尾部 (reconstruct が設定)
        self.labmap = {}           # va -> ラベル (領域内で idempotent)

    def nm(self, va, tag):
        self.cnt += 1
        n = "%%p1r_%x_%s_%s%d" % (va, self.salt, tag, self.cnt)
        # LIFTLIB-4: 値が「どの領域 block で定義されたか」を記録する。名前に埋めた
        # va はタグなので def の機械語 VA ではない (relay は他所の VA をタグに使う)。
        self.vdb[n] = self.cur_va
        return n

    # ---- LIFTLIB-2: 値の「支配」検証 (領域 DAG リフトの健全性) ----------------
    # 領域 block は head block の br からのみ入る。したがって領域内で参照できる値は
    #   (a) head の分割点より前の行で定義された値, (b) head を支配する block の値,
    #   (c) 自領域内で, 定義 block が使用 block を支配する値
    # のいずれかに限る。それ以外 (他 site の領域 block の値 / 別経路の load 結果) を
    # 参照すると clang が "Instruction does not dominate all uses!" で拒絕する。

    def _dom_func(self, a, b):
        """関数全体の機械語 block a が b を支配するか (cache 付き, LIFTLIB-4)。

        他 site の領域値 (`%p1r_<他salt>_…`) を採れるかどうかの判定に使う。
        領域単位の支配 (`_dom_region`) は「この領域の入口 D から」の支配なので,
        別領域が作った経路固有 SSA が自分たちの use に届くかを判定できない。
        機械語 CFG 全体で a が b を支配するなら, その値は use に必ず届く。
        """
        if self._domfull is None:
            cfg = self.mf.cfg()
            nodes = set(cfg)
            dom = {n: set(nodes) for n in nodes}
            dom[self.mf.start] = {self.mf.start}
            ch = True
            while ch:
                ch = False
                for n in nodes:
                    if n == self.mf.start:
                        continue
                    ps = cfg[n]["pred"]
                    if not ps:
                        continue
                    new = set(nodes)
                    for p in ps:
                        new &= dom[p]
                    new.add(n)
                    if new != dom[n]:
                        dom[n] = new
                        ch = True
            self._domfull = dom
        return a in self._domfull.get(b, ())

    def _dom_region(self, a, b):
        """自領域の機械語 block a が b を支配するか (入口 D からの支配, 1 fixpoint)。"""
        if self._domreg is None:
            cfg = self.mf.cfg()
            nodes = set(self.internal)
            dom = {n: set(nodes) for n in nodes}
            dom[self.D] = {self.D}
            ch = True
            while ch:
                ch = False
                for n in nodes:
                    if n == self.D:
                        continue
                    ps = [p for p in cfg[n]["pred"] if p in nodes]
                    if not ps:
                        continue
                    new = set(nodes)
                    for p in ps:
                        new &= dom[p]
                    new.add(n)
                    if new != dom[n]:
                        dom[n] = new
                        ch = True
            self._domreg = dom
        return a in self._domreg.get(b, ())

    def _value_ok(self, name, use_va):
        # ablation (SUBAGENT_RULES 規則 41): LL_NO_VDB_DOM=1 で LIFTLIB-4 の vdb ベース
        # 領域値支配判定を止め, LIFTLIB-3 迄の「名前に埋めた VA を def VA と誤認」に戻す。
        if os.environ.get("LL_NO_VDB_DOM") and P1R_NAME.match(name):
            m = P1R_NAME.match(name)
            if m.group(2) == self.salt:
                try:
                    dva = int(m.group(1), 16)
                except ValueError:
                    return False
                u = use_va if use_va is not None else self.cur_va
                if u is None:
                    return True
                db, ub = self.mf.block_of(dva), self.mf.block_of(u)
                return db == ub or self._dom_region(db, ub)
            return False
        """IR 値 name が use_va の地点から合法に参照できるか (支配の確認)。

        LIFTLIB-4: 領域値 (`%p1r_…`) の支配判定を修正した。従来は名前に埋めた VA
        (group(1)) を「値の機械語 VA」と見なしていたが, あれは **タグ** であって
        def の VA ではない (relay 値は他所の VA をタグに使う)。そのため正当な
        自領域値を「非支配」と誤判定し, leaf の phi 合成が落ちていた。
        自領域の値は `self.vdb` (定義 block) で, 他領域の値は IR の defs で判定する。
        """
        m = P1R_NAME.match(name)
        if m:
            u = use_va if use_va is not None else self.cur_va
            if m.group(2) == self.salt:
                # 自領域の値: vdb の定義 block が use block を支配するか
                dv = self.vdb.get(name)
                if dv is None:
                    return True             # 変換補助 (同一 block 内で消費)
                if u is None:
                    return True
                db, ub = self.mf.block_of(dv), self.mf.block_of(u)
                return db == ub or self._dom_region(db, ub)
            # 他 site の領域値: IR レベルの支配で判定する。領域値は経路固有 SSA を持つ
            # が, その def block が use を支配するなら (機械語 CFG 全体で) 合法。
            d = self.ix.defs.get(name)
            if d is None:
                return False
            dbi = d[0]
            if dbi == self.head_bi:
                return False                # 他領域が head を分割した値は別経路
            if not self.ix.dominates(dbi, self.head_bi):
                return False
            # さらに機械語レベルで, その領域の入口 (タグの VA) が use を支配する事
            try:
                dva = int(m.group(1), 16)
            except ValueError:
                return False
            if u is None:
                return False
            db, ub = self.mf.block_of(dva), self.mf.block_of(u)
            if db is None or ub is None or db not in self.mf.cfg() or ub not in self.mf.cfg():
                return False
            ok = db == ub or self._dom_func(db, ub)
            if ok:
                self.used("bind_other_region")
            return ok
        d = self.ix.defs.get(name)
        if d is None:
            return True                        # 引数 / alloca (入口 block) は全域を支配
        dbi, dli = d
        if dbi == self.head_bi:
            return dli < self.split_li          # head の分割点より前の行のみ
        return self.ix.dominates(dbi, self.head_bi)

    def _reissue_load(self, name, use_va, out):
        """非支配の reg2mem alloca load を「使用点で load を再発行」して値を取り戻す。

        RetDec は reg2mem 形式で `%x.reload = load T, ptr %x.reg2mem` を *使用側* block に
        置く。領域 (別 block) からその load 結果を参照すると非支配になるので, 同じ alloca を
        使用点で読み直す (reg2mem イディオムと同じ。alloca への store は全経路で使用点より前
        に行われるため値は不変)。取り戻せない場合は None。"""
        d = self.ix.defs.get(name)
        if d is None or out is None:
            return None
        dbi, dli = d
        ln = self.fn.blocks[dbi].lines[dli]
        m = re.match(r"^\s*%[\w$.\-]+ = load (\S+), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
        if not m:
            return None
        a = m.group(2)
        if a not in self.ix.allocas:
            return None                          # alloca 以外 (グローバル等) は再発行しない
        ty = m.group(1).rstrip(",")
        n = self.nm(use_va if use_va is not None else 0, "rl")
        out.append("  %s = load %s, ptr %s%s" % (n, ty, a, self.mod.tag(use_va or 0)))
        self.vdbld[n] = (a, ty)          # LIFTLIB-4: relay 兄弟 block 用に再発行できるよう覚える
        self.used("load_reissue")
        return (n, ty)

    def _checked(self, v, use_va, what, out=None):
        """値 v の使用可否を検証し, 非支配/他領域の値は Unsupported にする。"""
        if v is None:
            return v
        name = v[0]
        if name == "0" or not isinstance(name, str) or name.startswith("@@"):
            return v                                # 定数 / alloca 経由 load (入口 block)
        if not self._value_ok(name, use_va):
            nv = self._reissue_load(name, use_va, out)
            if nv is not None:
                return nv
            raise Unsupported("%s: 値 %s は非支配/他領域 (@%x)" % (what, name, use_va or 0))
        return v

    def lab(self, va):
        """領域 block のラベル。未請求の VA は素の dec_label_pc_<va> を請求し,
        他 site の領域 (または既存 IR) が既に使う VA は site 固有の接尾付き名にする。
        接尾付き名は 16 進のみのラベル判定 (exit_vas / has_label) から外れるため,
        後続 site はこの block を「未 lift」として自分の経路値で再 lift できる
        (領域 block は経路固有 SSA を持つゆえ, 他経路の辺の直入りを禁止する — LIFTLIB-2)。"""
        if va in self.labmap:
            return self.labmap[va]
        if va in _REGION_VAS or self.ix.has_label(va):
            n = "dec_label_pc_p1r%s_%x" % (self.salt, va)
        else:
            n = "dec_label_pc_%x" % va
            _REGION_VAS.add(va)
        self.labmap[va] = n
        return n

    def used(self, key):
        self.vocab[key] = self.vocab.get(key, 0) + 1

    def _call_ret_bits(self, reg, d, va, out):
        """call の戻り値を xmm のビット列として拾う (LIFTLIB-2)。

        RetDec は double 戻り (xmm0) を持つ CRT 数学関数を `call i64 @f()` と lift し,
        xmm0 の値を IR に残さない (bind xmm0 失敗の主因)。F6 (ir9_bootstraps) が
        exp/log/tan を i64 ビット列を授受する C port へ置換するため, これらの callee の
        i64 戻りは xmm0 のビット列そのものとして扱える。

        LIFTLIB-3: callee の選定を**機械語 (命名非依存)** に変えた。従来は
        function_1801b{4220,4900,ba860} という OTT 固有の名前パターンだったが,
        Binder.callee_returns_xmm0() を使い「全 ret で結果を xmm0 に書く callee」なら
        どの callee でも適用する (ott_e2e の m9_d* C port 名と合わせて緩和)。"""
        if not reg.startswith("xmm"):
            return None
        it = self.mf.insns.get(d)
        if it is None or not it.is_call or it.target is None:
            return None
        callee = "function_%x" % it.target
        ok_generic = self.b.callee_returns_xmm0(it.target)
        if not (ok_generic or callee.startswith("m9_d")):
            return None
        v = self.b.value_defined_at("rax", d)
        if v is None or v[1] not in ("i64", "i32"):
            return None
        n = self.nm(va, "cb")
        out.append("  %s = zext %s %s to i128%s" % (n, v[1], v[0], self.mod.tag(va)))
        self.used("bind_call_ret")
        return (n, "i128")

    def read_reg(self, st, reg, va, out, use_va=None):
        if reg in st:
            return st[reg]
        v = self._bind_dominating(reg, va)
        if v is None:
            v = self.resolve_bind(reg, va, out)      # LIFTLIB-2: cmov / 多定義 def からの値合成
        if v is None:
            v = self.b.bind_relaxed(reg, va)         # LIFTLIB-2: 生存側 store で覆う alloca の緩和読み
        if v is None:
            r = self.b.root_def(reg, va)
            if r[0] == "def":
                v = self._call_ret_bits(reg, r[1], va, out)
        if v is None:
            raise Unsupported("bind %s @%x" % (reg, va))
        # LIFTLIB-2: 非支配/他領域の値を弾く (clang の "does not dominate all uses" 防止)
        v = self._checked(v, va if use_va is None else use_va, "bind %s" % reg, out)
        if isinstance(v[0], str) and v[0].startswith("@@load:"):
            a = v[0][7:]
            n = self.nm(va, "ld")
            out.append("  %s = load %s, ptr %s%s" % (n, v[1], a, self.mod.tag(va)))
            v = (n, v[1])
        if reg.startswith("xmm") and v[1] != "i128":
            # xmm の追跡値は i128 に正規化 (f2 の %xmmK_bits 引数など i64 幅の bind 値)
            if v[0] == "0":
                v = ("0", "i128")
            else:
                n = self.nm(va, "xz")
                op = "trunc" if TYPE_BITS.get(v[1], 0) > 128 else "zext"
                out.append("  %s = %s %s %s to i128%s" % (n, op, v[1], v[0], self.mod.tag(va)))
                v = (n, "i128")
        st[reg] = v
        return v

    # ---- LIFTLIB-2: bind 失敗時の値合成 (phi 合成の bind 側) --------------------

    def _bind_dominating(self, reg, va):
        """bind 結果のうち領域の実行経路に流れる物のみ返す (支配検証)。

        領域は head block の br から入る。def が (a) 他 site の領域/tail/relay block
        (別経路の値のコピー), (b) head の split 点以降の行 (= 生存側尾部),
        (c) head を支配しない block — のいずれかにあると, 領域 block からの参照が
        非支配 (または別経路の値) になるので候補から外す。
        候補から外れた場合は None を返し, 呼出側 (read_reg) が cmov/多定義/def 命令の
        ローカル lift で値を取り戻す。"""
        v = self.b.bind(reg, va)
        if v is None:
            return None
        if not self._value_ok(v[0], va):
            return None
        r = self.b.root_def(reg, va)
        if r[0] != "def":
            return v
        for (bi, li, ln) in self.ix.instrs_at(r[1]):
            if IR.instr_dst(ln) is None:
                continue
            lab = self.fn.blocks[bi].label
            if lab.startswith("dec_label_pc_p1r") or lab.startswith("dec_label_pc_p1tail") \
                    or lab.startswith("dec_label_pc_p1relay") or lab.startswith("dec_label_pc_p1srelay"):
                return None
            mm = re.match(r"dec_label_pc_([0-9a-f]+)$", lab)
            if mm and int(mm.group(1), 16) in _REGION_VAS:
                return None
            if bi == self.head_bi and li >= self.split_li:
                return None
            if bi != self.head_bi and not self.ix.dominates(bi, self.head_bi):
                return None
            break
        return v

    def resolve_bind(self, reg, va, out):
        """bind が None を返した時の復元。失敗は None (呼出側で最終 fallback 判定)。"""
        try:
            r = self.b.root_def(reg, va)
            if r[0] == "multi":
                return self._resolve_multi(reg, r[1], va, out)
            if r[0] == "def":
                it = self.mf.insns.get(r[1])
                if it is not None and it.mnem.startswith("cmov") and len(it.ops) == 2:
                    return self._cmov_value(reg, r[1], va, out)
        except Unsupported:
            return None
        return None

    def _entry_value(self, reg):
        """関数入口の reg 値 (GPR 引数 / f2 付与の %xmmK_bits)。"""
        from ..mc import GPR_ARGS
        if reg in GPR_ARGS:
            k = GPR_ARGS.index(reg)
            if k < len(self.b.params):
                return (self.b.params[k][1], self.b.params[k][0])
            return None
        if reg.startswith("xmm"):
            k = int(reg[3:])
            for ty, nm2 in self.b.params:
                if nm2 == "%%xmm%d_bits" % k:
                    return (nm2, ty)
        return None

    def _cmov_value(self, reg, d, va, out):
        """cmovcc dst, src @d (RetDec が分岐化して IR に対応行が無い) を select で合成。

        条件: 直前の comis (IR には __asm_*comis* call が残る) から fcmp。
        src / 古い dst: 機械語到達定義から bind (st は汚さず新辞書で再帰)。"""
        it = self.mf.insns[d]
        cc = it.mnem[4:]
        fdefs = self.mf.defs_before(d, "flags")
        if len(fdefs) != 1 or not next(iter(fdefs)):
            raise Unsupported("cmov flag producer @%x" % d)
        A = next(iter(fdefs))
        calls = [(bi, li, ln) for (bi, li, ln) in self.ix.instrs_at(A) if COMIS_CALL.search(IR.strip_tokens(ln))]
        if not calls:
            raise Unsupported("cmov flag producer %x は comis でない" % A)
        pred = CC_PRED.get(cc)
        if pred is None:
            raise Unsupported("cmov cc %s" % cc)
        call_ln = calls[0][2]
        kind = parse_comis_call(call_ln)[0]
        key = ("cm", reg, d)
        if key in self._resolving:
            raise Unsupported("cmov cycle @%x" % d)
        self._resolving.add(key)
        try:
            bc = build_compare(self.mod, A, call_ln, kind, sfx="s%sc%x_%d" % (self.salt, d, self.cnt + 1))
            if bc is None:
                raise Unsupported("cmov comis operand form")
            ins, fa, fb, ty = bc
            out.extend(ins)
            tag = self.mod.tag(va)
            c = self.nm(va, "cc")
            out.append("  %s = fcmp %s %s %s, %s%s" % (c, pred, ty, fa, fb, tag))
            bits = it._ci.operands[0].size * 8
            st2 = {"__w": set(), "rsp": {}, "fl": None}
            v_src = self.read_reg(st2, _canon_reg(it._ci, it.ops[1].reg), d, out)
            v_dst = self.read_reg(st2, _canon_reg(it._ci, it.ops[0].reg), d, out)
            s = self._gpr_val_from(st2, v_src, va, out, bits=bits, tag=tag)
            dv = self._gpr_val_from(st2, v_dst, va, out, bits=bits, tag=tag)
            n = self.nm(va, "mv")
            wty = "i%d" % bits if bits < 64 else "i64"
            out.append("  %s = select i1 %s, i%d %s, i%d %s%s" % (n, c, bits, s, bits, dv, tag))
            self.used("bind_cmov")
            return (n, wty)
        finally:
            self._resolving.discard(key)

    def _setcc_value(self, reg, d, va, out):
        """`xor r,r ; ... ; setcc r8` (RetDec は結果を i1 で持つ) の r 全体値 = zext i1 → i64 (LIFTLIB-5)。

        GPR bind は i1 を弾くため多定義 bind が復元不能になっていた (tan @1801a9cd9 の r10 =
        入口 sign)。d と同一 block の直前 8 命令以内に同 reg の 32bit 以上のゼロ化 (xor r,r) がある時だけ上位 56bit = 0 と言える。"""
        if not leaf_ext("SETCC_I1"):
            return None
        it = self.mf.insns.get(d)
        if it is None or not it.mnem.startswith("set") or len(it.ops) != 1 or it.ops[0].type != 1:
            return None
        if _canon_reg(it._ci, it.ops[0].reg) != reg:
            return None
        # d と同一の機械語 block 内に限る: block 境界を跨ぐと別 pred の xor を「ゼロ化済み」と誤認し,
        # setcc を通らない経路の上位 56bit が 0 と保証できない (silent miscompile)
        vas = self.mf.cfg()[self.mf.block_of(d)]["vas"]
        k = vas.index(d)
        zeroed = False
        for pv in reversed(vas[max(0, k - 8):k]):
            p = self.mf.insns[pv]
            if p.mnem == "xor" and len(p.ops) == 2 and p.ops[0].type == 1 and p.ops[1].type == 1 \
                    and p.ops[0].reg == p.ops[1].reg and _canon_reg(p._ci, p.ops[0].reg) == reg \
                    and p._ci.operands[0].size >= 4:       # 8/16bit xor は上位 bit を消さない
                zeroed = True
                break
            if reg in p.writes:
                break
        if not zeroed:
            return None
        for (bi, li, ln) in self.ix.instrs_at(d):
            dst = IR.instr_dst(ln)
            if not dst or result_type(ln) != "i1" or self.b._is_region_dst(dst):
                continue
            if not self._value_ok(dst, va):
                continue
            n = self.nm(va, "sz")
            out.append("  %s = zext i1 %s to i64%s" % (n, dst, self.mod.tag(va)))
            self.used("setcc_i1")
            return (n, "i64")
        return None

    def _def_site_lift(self, reg, d, va, out):
        """落とされた経路上の def 命令 1 個をその場で lift して値を復元する
        (SSE 算術 / GPR mov・即値 / rip 基準 load など, 値を生む単一命令)。"""
        it = self.mf.insns.get(d)
        if it is None or it.is_jcc or it.is_jmp or it.is_ret or it.is_call or it.indirect:
            return None
        if it.mnem.startswith("cmov") or (it.mem and it.mem["write"]):
            return None
        if it.mnem.lstrip("v") in ("comisd", "comiss", "ucomisd", "ucomiss", "cmp", "test"):
            return None                              # 値を生まない (flag のみ)
        key = ("dl", reg, d)
        if key in self._resolving:
            return None
        self._resolving.add(key)
        try:
            ops = _reg_ops(it)
            st2 = {"__w": set(), "rsp": {}, "fl": None}
            body = []
            if it.mnem in _MOV_RR and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "reg":
                v = self.read_reg(st2, ops[1][1], d, body)
                st2[ops[0][1]] = v
                st2["__w"].add(ops[0][1])
            elif not self.lift_data_insn(it, ops, st2, body, self.mod.tag(d)):
                return None
            v = st2.get(reg)
            if v is None:
                return None
            out.extend(body)
            self.used("bind_deflift")
            return v
        except Unsupported:
            return None
        finally:
            self._resolving.discard(key)

    def _resolve_multi(self, reg, defs, va, out):
        """多定義 bind: 各 def の値を復元し, 全 def が同一値の時だけ採用する (LIFTLIB-2)。

        不一致の場合はここでは合成しない (誤った値の選択より unsupported を優先)。
        領域内合流による多定義は collect/merge_in の reg2mem 合成が正しい値を選ぶ。"""
        vals = []
        if leaf_ext("REGION_DEFS"):
            # LIFTLIB-5: 領域は D からしか入らない。生存側 S (領域外) の命令だけが書く def は
            # この経路に流れないので除外する (def が領域内 block か, 分岐点 J に到達する def のみ残す)。
            at_j = self.mf.defs_before(self.J, reg)
            keep = {d for d in defs
                    if d in at_j or (d and self.mf.block_of(d) in self.internal)}
            if keep and keep != set(defs):
                self.used("multi_region_defs")
                defs = keep
        for d in sorted(defs):
            if d == 0:
                v = self._entry_value(reg)
            else:
                v = self.b.value_defined_at(reg, d)
                # LIFTLIB-2: 非支配/他 site 領域の IR 値は採用せず, この def 命令を
                # ローカルに lift して値を取り戻す (領域 block は経路固有 SSA を持つため)
                if v is not None and not self._value_ok(v[0], va):
                    v = None
                if v is None:
                    v = self.b.synthetic_def(reg, d)
                if v is None:
                    v = self._setcc_value(reg, d, va, out)
                if v is None:
                    it = self.mf.insns.get(d)
                    if it is not None and it.mnem.startswith("cmov") and len(it.ops) == 2:
                        v = self._cmov_value(reg, d, va, out)
                if v is None:
                    v = self._def_site_lift(reg, d, va, out)
            if v is None:
                raise Unsupported("multi-def %s@%x: def %x を復元不能" % (reg, va, d))
            vals.append(v)
        if all(v == vals[0] for v in vals):
            self.used("bind_multi_eq")
            return vals[0]
        raise Unsupported("multi-def %s@%x: %d 値が不一致" % (reg, va, len(set(map(str, vals)))))

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
                bv = self.resolve_bind(dst, va, out)
            if bv is None:
                # 入口 callee-saved xmm の復元 (RetDec IR も alloca 未 store = B1 後 0)。
                # ハーネスも入口 xmm4-15 を 0 初期化するため 0 を復元値にする (LIFTLIB-2)
                bv = ("0", "i128")
                self.used("rsp_restore_zero")
            if isinstance(bv[0], str) and bv[0].startswith("@@load:"):
                n = self.nm(va, "ld")
                out.append("  %s = load %s, ptr %s%s" % (n, bv[1], bv[0][7:], self.mod.tag(va)))
                bv = (n, bv[1])
            st[dst] = bv
            st["__w"].add(dst)
            self.used("rsp_restore_bind")
            return True
        raise Unsupported("rsp load %s size %d" % (base, m["size"]))

    def _rsp_gpr(self, it, st, out, va, tag, write):
        """64bit GPR の rsp slot spill/reload (LIFTLIB-5)。xmm slot と同じ head alloca (i64) 経由。
        slot が領域内で書かれていない reload は Unsupported (入口/他経路の値を推測しない)。"""
        m = it.mem
        if m["index"] or m["seg"]:
            raise Unsupported("rsp slot form %s" % it.op_str)
        off = m["disp"]
        ap = self.rsp_allocas.get(off)
        if write:
            if ap is None:
                ap = "%%p1r_%x_rsp%x" % (self.D, off & 0xFFFFFFFF)
                self.rsp_allocas[off] = ap
                self.rsp_alloca_lines.append("  %s = alloca i64" % ap)
            x = self._gpr_val(st, _canon_reg(it._ci, it.ops[1].reg), va, out)
            out.append("  store i64 %s, ptr %s, align 4%s" % (x, ap, tag))
            st.setdefault("__gw", set()).add(off)
            self.used("rsp_gpr_store")
            return True
        if ap is None or off not in st.get("__gw", ()):
            raise Unsupported("rsp gpr reload @%x: slot %#x が領域内の全経路で store 済みでない" % (va, off))
        dst = _canon_reg(it._ci, it.ops[0].reg)
        n = self.nm(va, "gl")
        out.append("  %s = load i64, ptr %s, align 4%s" % (n, ap, tag))
        st[dst] = (n, "i64")
        st["__w"].add(dst)
        self.used("rsp_gpr_load")
        return True

    def _lift_call(self, it, st, out, va, tag):
        """断片内 call。declare (RetDec) の引数型列を (rcx,rdx,r8,r9) に対応付け,
        第5引数以降は call site の [rsp+0x20+8i] slot (callee 側スタック引数) から。
        f2 が付与した `%xmmK_bits` 引数 (callee の入口 xmm) は領域が追跡する xmmK 値を渡す
        (LIFTLIB-2: f2 callee 相を p1 前に流すため, 領域内 call も引数が整合する)。
        戻り: rax = 宣言の戻り型。xmm0 は「call 戻り値の bits」を仮置きする
        (F6/leafabi が callee を bits 戻りに差替えた経路と整合; raw では survivor 経路と同品質)。"""
        callee = "function_%x" % it.target
        decl = self.mod.declares().get(callee)
        dfn = self.mod.func(callee)
        if decl is None and dfn is not None:
            # define 済み callee: define の引数列を使う (declare 追加はしない — 再定義エラー回避)
            m = IR.DEFINE.match(dfn.sig)
            ret = m.group(1).split()[0]
            decl = (ret, ", ".join("%s %s" % (ty, nm) for ty, nm in dfn.params()), None)
        elif decl is None:
            self.mod.add_declare("declare i64 @%s() local_unnamed_addr" % callee)
            ret, argtys = "i64", []
        else:
            ret = decl[0]
        args_full = [a.strip() for a in IR.split_args(decl[1]) if a.strip()] if decl else []
        argtys = [a.split()[0] for a in args_full]
        argnames = [a.split()[1] if len(a.split()) > 1 else "" for a in args_full]
        gprs = ["rcx", "rdx", "r8", "r9"]
        if len(argtys) > 8:
            raise Unsupported("call args %d" % len(argtys))
        vals = []
        slots = st.get("rsp", {})
        gi = 0
        for i, ty in enumerate(argtys):
            mx = re.match(r"^%xmm(\d+)_bits$", argnames[i] or "")
            if mx:
                # f2 付与の入口 xmm 引数: 領域が追跡する xmm 値 (i128) の下位 bits
                k = int(mx.group(1))
                x = self.read_reg(st, "xmm%d" % k, va, out)
                if x[1] != "i128":
                    raise Unsupported("call xmm%d arg type %s" % (k, x[1]))
                if ty == "i128":
                    vals.append("i128 %s" % x[0])
                    continue
                t = self.nm(va, "ca")
                out.append("  %s = trunc i128 %s to %s%s" % (t, x[0], ty, tag))
                vals.append("%s %s" % (ty, t))
                continue
            if ty == "ptr" or ty.startswith("i"):
                bits = {"ptr": 64}.get(ty) or self._ITyw.get(ty, 64)
                if gi < 4:
                    v = self._gpr_val(st, gprs[gi], va, out, bits=bits)
                else:
                    key = 0x20 + 8 * (gi - 4)
                    if key not in slots:
                        raise Unsupported("call stack arg %d (slot %x 未追跡)" % (gi + 1, key))
                    v = self._gpr_val_from(st, slots[key], va, out, bits=bits, tag=tag)
                gi += 1
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
        for r in ("rcx", "rdx", "r8", "r9"):
            st.pop(r, None)
        st["__w"].difference_update(("rcx", "rdx", "r8", "r9"))
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
        if fl[0] == "bsrzf":
            src, bits = fl[1]
            out.append("  %s = icmp eq i%d %s, 0%s" % (n, bits, src, tag))
            return n
        if fl[0] == "shrcf":
            raise Unsupported("shr cl flag: ZF は未実装 @%x" % va)
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
        if fl[0] == "bsrzf":
            if cc not in ("e", "z", "ne", "nz"):
                raise Unsupported("bsr flag: cc %s は ZF 以外 (CF/SF/OF 未定義) @%x" % (cc, va))
            src, bits = fl[1]
            pred = "eq" if cc in ("e", "z") else "ne"
            n = self.nm(va, "fc")
            out.append("  %s = icmp %s i%d %s, 0%s" % (n, pred, bits, src, tag))
            return n
        if fl[0] == "shrcf":
            if cc not in ("b", "c", "nae", "ae", "nb", "nc"):
                raise Unsupported("shr cl flag: cc %s は CF 以外 (ZF/SF/OF 未実装) @%x" % (cc, va))
            cf = fl[1][0]
            if cc in ("b", "c", "nae"):
                return cf
            n = self.nm(va, "fc")
            out.append("  %s = xor i1 %s, true%s" % (n, cf, tag))
            return n
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
        if fl[0] == "bsrzf":
            raise Unsupported("bsr flag: CF は未定義 @%x" % va)
        if fl[0] == "shrcf":
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

    def _int_jcc_cond(self, it, st, out, va, tag):
        """整数フラグ分岐 (cmp/test + jcc) の条件 i1 を生成。comis 系は fcmp へ流用。"""
        fl = st.get("fl")
        if fl is None:
            raise Unsupported("jcc without flag producer @%x" % va)
        cc = it.cc
        c = self._flag_cc_i1(st, cc, out, va, tag)
        if c is not None:
            self.used("int_jcc")
            return c
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
        self.used("int_jcc")
        return c

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
            # LIFTLIB-5: 64bit GPR の spill/reload (mov [rsp+k], r64 / mov r64, [rsp+k])
            if m == "mov" and leaf_ext("GPR_SPILL") and mem["size"] == 8 and len(it.ops) == 2 \
                    and (it.ops[1].type == 1 if mem["write"] else it.ops[0].type == 1):
                return self._rsp_gpr(it, st, out, va, tag, write=mem["write"])
        # 断片内 call
        if it.is_call and it.target is not None and not mem:
            return self._lift_call(it, st, out, va, tag)
        # setcc (整数フラグ → GPR) — setcc は operand 1 値 (r/m8)
        if m.startswith("set") and len(ops) == 1 and ops[0][0] == "reg" and not mem:
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
            return True        # --- GPR ALU (RMW): or/and/xor/add/sub r, r|imm|mem / inc|dec r
        if ((m in self._GPR_ALU and len(ops) == 2) or (m in ("inc", "dec") and len(ops) == 1)) \
                and ops[0][0] == "reg" \
                and ops[0][1].startswith("r") and not mem:
            dst = ops[0][1]
            if dst == "rsp":
                if m in ("add", "sub") and ops[1][0] == "imm":
                    self.used("rsp_adj")      # スタックポインタ調整は値に影響しない (slot は disp 基準)
                    return True
                raise Unsupported("rsp alu %s" % it.op_str)
            bits = it._ci.operands[0].size * 8
            a = self._gpr_val(st, dst, va, out, bits=bits)
            if m in ("inc", "dec"):
                b = "1"
            elif ops[1][0] == "reg":
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
        # --- adc r, imm (LIFTLIB-31): dst = dst + imm + CF。入力 CF は flag 状態から読む (CF を作れない経路は Unsupported)。
        if m == "adc" and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "imm" and not mem:
            dst = ops[0][1]
            if dst == "rsp" or not dst.startswith("r"):
                raise Unsupported("adc dst %s" % dst)
            bits = it._ci.operands[0].size * 8
            ity = "i%d" % bits
            a = self._gpr_val(st, dst, va, out, bits=bits)
            imm = ops[1][1]
            if bits < 64:
                imm &= (1 << bits) - 1
            elif imm >= (1 << 63):
                imm -= (1 << 64)
            cf = self._flag_cf_i1(st, out, va, tag)
            cz = self.nm(va, "ac")
            out.append("  %s = zext i1 %s to %s%s" % (cz, cf, ity, tag))
            s1 = self.nm(va, "as")
            out.append("  %s = add %s %s, %s%s" % (s1, ity, a, imm, tag))
            n = self.nm(va, "al")
            out.append("  %s = add %s %s, %s%s" % (n, ity, s1, cz, tag))
            st[dst] = (n, ity if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = None                    # adc は全フラグを再定義する (後続 jcc は未対応)
            self.used("adc")
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
        # --- bsr r, r (LIFTLIB-26): ZF = (src==0)。src==0 のとき dst は前値を保つ (Intel 未定義・実装依存の扱いを固定)。
        #     flag 状態は専用種別 "bsrzf" (ZF だけを読める)。CF/SF/OF は bsr で未定義のため、e/ne/z/nz 以外の cc は Unsupported。
        if m == "bsr" and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "reg" and not mem:
            bits = it._ci.operands[0].size * 8
            if bits not in (32, 64):
                return False
            ity = "i%d" % bits
            dst = ops[0][1]
            src = self._gpr_val(st, ops[1][1], va, out, bits=bits)
            old = self._gpr_val(st, dst, va, out, bits=bits)
            decl = "llvm.ctlz.%s" % ity
            if decl not in self.mod.declares():
                self.mod.add_declare("declare %s @%s(%s, i1) nounwind readnone speculatable" % (ity, decl, ity))
            ctl = self.nm(va, "bc")
            out.append("  %s = call %s @%s(%s %s, i1 true)%s" % (ctl, ity, decl, ity, src, tag))
            ix = self.nm(va, "bi")
            out.append("  %s = sub %s %d, %s%s" % (ix, ity, bits - 1, ctl, tag))
            cz = self.nm(va, "bz")
            out.append("  %s = icmp eq %s %s, 0%s" % (cz, ity, src, tag))
            n = self.nm(va, "bs")
            out.append("  %s = select i1 %s, %s %s, %s %s%s" % (n, cz, ity, old, ity, ix, tag))
            st[dst] = (n, ity if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = ("bsrzf", (src, bits))
            self.used("bsr")
            return True
        # --- shr r, cl (LIFTLIB-30 / #6078): count=cl&(bits-1)。count==0 は値・フラグ不変。
        #     CF = count!=0 のとき src の bit (count-1)、count==0 のとき前の CF。count は実行時値なので CF は i1 として
        #     eager に作り flag 種別 "shrcf" に載せる (CF だけ読める)。前の CF が決まらない (flag 状態なし) ときは Unsupported。
        if m == "shr" and len(ops) == 2 and ops[0][0] == "reg" and ops[1] == ("reg", "rcx") and not mem:
            bits = it._ci.operands[0].size * 8
            if bits not in (32, 64):
                return False
            ity = "i%d" % bits
            dst = ops[0][1]
            prev = self._flag_cf_i1(st, out, va, tag)
            a = self._gpr_val(st, dst, va, out, bits=bits)
            c = self._gpr_val(st, "rcx", va, out, bits=bits)
            cnt = self.nm(va, "sk")
            out.append("  %s = and %s %s, %d%s" % (cnt, ity, c, bits - 1, tag))
            nz = self.nm(va, "snz")
            out.append("  %s = icmp ne %s %s, 0%s" % (nz, ity, cnt, tag))
            cm1 = self.nm(va, "sm")
            out.append("  %s = sub %s %s, 1%s" % (cm1, ity, cnt, tag))
            cs = self.nm(va, "ss")
            out.append("  %s = select i1 %s, %s %s, %s 0%s" % (cs, nz, ity, cm1, ity, tag))
            bt = self.nm(va, "sb")
            out.append("  %s = lshr %s %s, %s%s" % (bt, ity, a, cs, tag))
            b1 = self.nm(va, "sbi")
            out.append("  %s = and %s %s, 1%s" % (b1, ity, bt, tag))
            bc = self.nm(va, "sbc")
            out.append("  %s = icmp ne %s %s, 0%s" % (bc, ity, b1, tag))
            cf = self.nm(va, "scf")
            out.append("  %s = select i1 %s, i1 %s, i1 %s%s" % (cf, nz, bc, prev, tag))
            n = self.nm(va, "sr")
            out.append("  %s = lshr %s %s, %s%s" % (n, ity, a, cnt, tag))
            st[dst] = (n, ity if bits < 64 else "i64")
            st["__w"].add(dst)
            st["fl"] = ("shrcf", (cf, bits))
            self.used("shift_cl")
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
        """機械語 start から基本ブロック終端まで lift し (本体行, 終端行) を返す。
        辺は再帰 lift せず edge_target で行き先ラベルを解決する (LIFTLIB-2: DAG lift)。
        st: "__w"=書込 reg, "rsp"=rsp slot 値, "fl"=flag 状態 (comis/整数 cmp)。"""
        mf, mod = self.mf, self.mod
        out = []
        self.cur_va = start          # LIFTLIB-2: 値の支配検証の基準 block
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
                else:
                    c = self._int_jcc_cond(it, st, out, va, tag)
                lt = self.edge_target(it.target, st, va)
                lf = self.edge_target(it.next, st, va)
                return out, "  br i1 %s, label %%%s, label %%%s%s" % (c, lt, lf, tag)
            elif it.is_ret:
                # 断片内 ret: rax は追跡値 (無ければ 0)。実値は xmm0 戻り (leafabi が搬送)
                rax = st.get("rax")
                rv = rax[0] if rax else "0"
                ty = rax[1] if rax else "i64"
                if ty != "i64":
                    n = self.nm(va, "rr")
                    out.append("  %s = zext %s %s to i64%s" % (n, ty, rv, tag))
                    rv = n
                self.used("ret")
                return out, "  ret i64 %s%s" % (rv, tag)
            elif m == "jmp" and it.target is not None:
                lt = self.edge_target(it.target, st, va)
                return out, "  br label %%%s%s" % (lt, tag)
            elif m.startswith("nop"):
                pass
            elif self.lift_data_insn(it, ops, st, out, tag):
                pass
            else:
                raise Unsupported("%x: %s %s" % (va, m, it.op_str))
            va = it.next
            if va in self.leaders:
                lt = self.edge_target(va, st, va)
                return out, "  br label %%%s" % lt

    # ---- LIFTLIB-2: 領域の収集 (DAG) と reg2mem 合成 ----------------------------

    def block_live_in(self):
        """全機械語 block 開始点の live-in (1 fixpoint で計算して cache)。"""
        if self._blk_live is None:
            self._blk_live = _all_blocks_live_in(self.mf)
        return self._blk_live

    @staticmethod
    def _trackable(reg):
        """合成対象にする reg (GPR は rsp 除く / xmm)。"""
        return reg.startswith("xmm") or (reg.startswith("r") and reg != "rsp")

    def preterm_lines(self, va):
        return self.join_stores.setdefault(va, [])

    def collect(self):
        """D から機械語 CFG を DFS し領域 block 集合を求める。

        出口 = 既存 IR ラベル (exit_vas) と生存側 S。back edge (ループ) は unsupported。
        領域内 block の機械語 pred は領域内か入口 D のみ (それ以外は合流構造が
        RetDec の block 境界と矛盾するため unsupported)。"""
        cfg = self.mf.cfg()
        color, internal, order = {}, set(), []
        stack = [(self.D, False)]
        while stack:
            va, done = stack.pop()
            if done:
                color[va] = 2
                order.append(va)
                continue
            if va == self.S and not self.S_is_label:
                continue
            if va in self.exit_vas:
                continue
            if va not in self.mf.insns:
                raise Unsupported("edge outside function @%x" % va)
            c = color.get(va, 0)
            if c == 1:
                raise Unsupported("region loop @%x" % va)
            if c == 2:
                continue
            color[va] = 1
            internal.add(va)
            stack.append((va, True))
            for s in cfg[va]["succ"]:
                stack.append((s, False))
        order.reverse()
        # 注: 領域内 block の機械語 pred に領域外 (生存側) block が在ってもよい。
        # 生存側の IR 辺は既存ラベル (出口) 宛であり, 本領域が作る IR block への
        # 辺は領域内の辺だけである (merge_in は領域内 pred だけを合成する)。
        self.internal = internal
        self.topo = order

    def run(self, D, st0):
        """領域を構築し, 入口 (D) block のラベルを返す。IR への反映は呼出側 (reconstruct)。"""
        self.collect()
        if not self.internal:
            return self.edge_target(D, st0, D)
        entry = None
        for va in self.topo:
            self.cur_va = va          # LIFTLIB-4: merge_in が合成する値の def block 基準
            if va == D:
                st = {k: (set(v) if k in ("__w", "__gw") else (dict(v) if k == "rsp" else v)) for k, v in st0.items()}
                pre = []
            else:
                st, pre = self.merge_in(va)
            body, term = self.lift_block(va, st)
            self.bodies[va] = pre + body
            self.terms[va] = term
            self.out_states[va] = st
            if va == D:
                entry = self.lab(va)
        for va in self.topo:
            self.blocks.append((self.lab(va), self.bodies[va] + self.preterm_lines(va) + [self.terms[va]]))
        return entry

    def merge_in(self, va):
        """合流点の入力状態を pred 状態から合成する。戻り値 (st, 先頭に置く行)。

        pred 間で一致する reg はその値, 不一致の reg は関数入口 alloca への
        store (各 pred 終端) + 合流 block 先頭 load で合成 (reg2mem phi)。"""
        cfg = self.mf.cfg()
        preds = [p for p in cfg[va]["pred"] if p in self.internal]
        pst = [self.out_states[p] for p in preds]
        st = {"__w": set(), "fl": None, "rsp": {}, "__gw": set()}
        if pst:
            st["__w"] = set().union(*[s["__w"] for s in pst])
            # GPR spill slot は全 pred 経路で store 済みの slot だけ reload 可 (片経路だけの store は未初期化 alloca を読む)
            st["__gw"] = set.intersection(*[set(s.get("__gw", ())) for s in pst])
            fls = [s.get("fl") for s in pst]
            st["fl"] = fls[0] if all(f == fls[0] for f in fls) else None
            rsps = [s.get("rsp", {}) for s in pst]
            common = set.intersection(*[set(r) for r in rsps]) if rsps else set()
            for off in sorted(common):
                vs = [r[off] for r in rsps]
                if all(v == vs[0] for v in vs):
                    st["rsp"][off] = vs[0]
        pre = []
        # 合成対象: pred 状態が持つ reg 全体 (machine live-in に限定しない —
        # IR レベルの need (f2 の %xmmK_bits call 引数など) は機械語 liveness に現れないため)
        cands = sorted({r for s in pst for r in s if self._trackable(r)} - set(st))
        for r in cands:
            if not all(r in s for s in pst):
                # 持っていない pred の終端で到達値を束縛してから合成する
                dead_skip = False
                for s, p in zip(pst, preds):
                    if r not in s:
                        try:
                            self.read_reg(s, r, cfg[p]["vas"][-1], self.preterm_lines(p), use_va=p)
                        except Unsupported:
                            # LIFTLIB-5: 入口値 (f2 引数なし) など束縛不能でも, 合流点で
                            # live でない reg (直後に上書きされる) なら合成不要 → 捨てる
                            if not leaf_ext("DEAD_JOIN") or r in self.block_live_in().get(va, set()):
                                raise
                            dead_skip = True
                            break
                if dead_skip:
                    self.used("join_dead_skip")
                    continue
            vals = [s[r] for s in pst]
            vals = [self._checked(v, p, "merge %s" % r, self.preterm_lines(p))
                    for p, v in zip(preds, vals)]
            if all(v == vals[0] for v in vals):
                st[r] = vals[0]
            else:
                st[r] = self._join_value(va, r, vals, preds, pre)
        return st, pre

    def _join_ty(self, r, vals):
        tys = {v[1] for v in vals}
        if tys == {"i128"}:
            return "i128"
        if tys <= {"i8", "i16", "i32", "i64", "i128"}:
            # 混在 (例: xmm が f2 引数の i64 と helper 結果の i128) は最広幅へ揃える
            return "i128" if "i128" in tys else "i64"
        raise Unsupported("join %s: 型混合 %s" % (r, sorted(tys)))

    def _to_ty(self, p, v, ty):
        """値を alloca の型へ変換 (変換行は pred p の終端前に差し込む)。"""
        name, vty = v
        if vty == ty or name == "0":
            return name
        n = self.nm(p, "jv")
        op = "trunc" if TYPE_BITS.get(vty, 0) > TYPE_BITS.get(ty, 0) else "zext"
        self.preterm_lines(p).append("  %s = %s %s %s to %s" % (n, op, vty, name, ty))
        return n

    def _join_value(self, va, r, vals, preds, out):
        """pred 値が不一致の reg を「入口 alloca + 各 pred 終端 store + 先頭 load」で合成。"""
        ty = self._join_ty(r, vals)
        key = (va, r)
        a = self.join_allocas.get(key)
        if a is None:
            n0 = 9000
            while "%%%s.%d.reg2mem" % (r, n0) in self.ix.allocas or \
                    "%%%s.%d.reg2mem" % (r, n0) in self.join_allocas.values():
                n0 += 1
            a = "%%%s.%d.reg2mem" % (r, n0)
            self.join_allocas[key] = a
            self.join_alloca_lines.append("  %s = alloca %s" % (a, ty))
            self.join_alloca_lines.append("  store %s 0, ptr %s" % (ty, a))
        for p, v in zip(preds, vals):
            vv = self._to_ty(p, v, ty)
            self.preterm_lines(p).append("  store %s %s, ptr %s" % (ty, vv, a))
        n = self.nm(va, "jn")
        out.append("  %s = load %s, ptr %s%s" % (n, ty, a, self.mod.tag(va)))
        self.used("phi_join")
        return (n, ty)

    def edge_target(self, va, st, from_va):
        """辺 -> 行き先ラベル。既存 IR ラベル = relay (merge store), S = 生存側尾部,
        領域内 = そのままのラベル (合流は merge_in が扱う)。"""
        if va == self.S and not self.S_is_label:
            bad = (st["__w"] - {"flags"}) & self.live_at_S
            if bad:
                # LIFTLIB-2: tail が reg2mem alloca で受ける reg は store で運べる
                cov = self._tail_alloca_regs()
                if bad - cov:
                    raise Unsupported("region writes %s live into survivor" % sorted(bad - cov))
                self.relay_n += 1
                relay = "dec_label_pc_p1srelay_%s_%d" % (self.salt, self.relay_n)
                pre = []
                self._emit_tail_stores(st, pre)
                self.blocks.append((relay, pre + ["  br label %%dec_label_pc_%x" % va]))
                self.used("relay_s")
                return relay
            return "dec_label_pc_%x" % va
        if va in self.exit_vas:
            if va == self.D and getattr(self, "join_label", None):
                # CAB-238 §6: 脱落側入口 = head block 自身のラベル。
                # relay の行き先は tail を割った合流点 block (head 自身ではない — 自己辺禁止)
                self.relay_n += 1
                relay = "dec_label_pc_p1relay_%s_%d" % (self.salt, self.relay_n)
                pre = []
                self.emit_merge_stores(va, st, pre)
                for (_u, ty, a, r) in getattr(self, "join_merge", None) or []:
                    # 脱落側経路でのレジスタ到達値を, 合流点が読む alloca に store する
                    # (bind 基準は分岐点 J — D にすると生存側尾部の def まで戻ってしまう)
                    try:
                        v = self.read_reg(st, r, self.J, pre)
                        pre.append("  store %s %s, ptr %s" % (ty, self._conv_inline(pre, v, ty), a))
                        self.used("join_merge_store")
                    except Unsupported as _e:
                        raise Unsupported("join merge %s @%x: 脱落側の値を解決できない (%s)"
                                          % (r, self.J, _e))
                self.blocks.append((relay, pre + ["  br label %%%s" % self.join_label]))
                self.used("relay")
                return relay
            self.relay_n += 1
            relay = "dec_label_pc_p1relay_%s_%d" % (self.salt, self.relay_n)
            pre = []
            self.emit_merge_stores(va, st, pre)
            self.blocks.append((relay, pre + ["  br label %%dec_label_pc_%x" % va]))
            self.used("relay")
            return relay
        return self.lab(va)

    def _tail_alloca_regs(self):
        """tail (生存側尾部) が reg2mem alloca の load で受ける reg 集合。"""
        if not hasattr(self, "_tail_cov"):
            cov = set()
            for ln in getattr(self, "tail_lines", []):
                mm = re.match(r"^\s*%[\w$.\-]+ = load \S+, ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
                if mm and mm.group(1).endswith(".reg2mem"):
                    rm = re.match(r"^%(r[a-z0-9]+|xmm\d+)\.\d+(?:\.in)?\.reg2mem$", mm.group(1))
                    if rm:
                        cov.add(rm.group(1))
            self._tail_cov = cov
        return self._tail_cov

    def _emit_tail_stores(self, st, out):
        """tail の reg2mem alloca (load がある物) へ, 領域が書いた reg の値を store する。"""
        for ln in getattr(self, "tail_lines", []):
            mm = re.match(r"^\s*%[\w$.\-]+ = load (\S+), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
            if not mm or not mm.group(2).endswith(".reg2mem"):
                continue
            ty, a = mm.group(1).rstrip(","), mm.group(2)
            rm = re.match(r"^%(r[a-z0-9]+|xmm\d+)\.\d+(?:\.in)?\.reg2mem$", a)
            if not rm or rm.group(1) not in st["__w"]:
                continue
            val = self._conv_inline(out, st[rm.group(1)], ty)
            out.append("  store %s %s, ptr %s" % (ty, val, a))

    def _conv_inline(self, out, v, ty):
        """(name, ty) を alloca/load の型 ty へ (変換行は out へ)。定数 0 は型不問。"""
        name, vty = v
        if vty == ty or name == "0":
            return name
        n = self.nm(0, "cv")
        op = "trunc" if TYPE_BITS.get(vty, 0) > TYPE_BITS.get(ty, 0) else "zext"
        out.append("  %s = %s %s %s to %s" % (n, op, vty, name, ty))
        return n

    def _for_block(self, v, out):
        """値 v を「この block から合法に参照できる形」にして返す (LIFTLIB-4)。

        relay block は 1 終点ごとに新規に作られる。`_reissue_load` が *或る pred の*
        終端前に load を挿入して作った値は, その兄弟 relay block からは非支配になる
        (clang "does not dominate all uses")。兄弟に同じ値を store する必要があるときは
        その relay 自身でもう一度 load し直す。"""
        if out is None:
            return v
        nm = v[0] if isinstance(v, tuple) else None
        if nm in self.vdbld:
            src = self.vdb.get(nm)
            if src is not None and src != self.cur_va:
                a, ty = self.vdbld[nm]
                n2 = self.nm(self.cur_va or 0, "rl")
                out.append("  %s = load %s, ptr %s" % (n2, ty, a))
                self.vdbld[n2] = (a, ty)
                self.used("load_reissue2")
                return (n2, v[1])
        return v

    def emit_merge_stores(self, L, st, out):
        """既存ブロック L の先頭で load される reg2mem alloca へ, この辺の値を store する。"""
        fn, ix = self.fn, self.ix
        # join split (CAB-238 §6): 脱落側入口が head block 自身のラベルだった場合,
        # 合流点は tail を割った後ろ block なのでそちらを走査する
        scan = self.join_scan if (L == self.D and getattr(self, "join_label", None)) else None
        if scan is None:
            bi = ix.label_idx.get("dec_label_pc_%x" % L)
            if bi is None:
                raise Unsupported("exit label %x" % L)
            scan = fn.blocks[bi].lines
        for ln in scan:
            mm = re.match(r"^\s*%[\w$.\-]+ = load (\S+), ptr (%[\w$.\-]+)", IR.strip_tokens(ln))
            if not mm:
                continue
            ty, a = mm.group(1).rstrip(","), mm.group(2)
            if not a.endswith(".reg2mem"):
                continue
            rm = re.match(r"^%(r[a-z0-9]+|xmm\d+)\.\d+(?:\.in)?\.reg2mem$", a)
            val = None
            if rm and rm.group(1) in st["__w"]:
                val = self._conv_inline(out, self._for_block(st[rm.group(1)], out), ty)
            elif rm:
                # LIFTLIB-2: 生存側 store の無い alloca は, この辺の到達値 (機械語 bind) で埋める
                try:
                    v = self.read_reg(st, rm.group(1), L, out)
                    val = self._conv_inline(out, self._for_block(v, out), ty)
                    self.used("relay_bind")
                except Unsupported:
                    val = None
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
    # 他 site の領域が lift 済みの VA は「未 lift」扱い (自分の経路値で再 lift する)
    pT, pF = ix.present(T) and T not in _REGION_VAS, ix.present(F) and F not in _REGION_VAS
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
    reg = Region(mod, fn, mf, binder, rec, S, D, J)
    reg.ix = ix
    reg.exit_vas = set()
    for lab2, bi in ix.label_idx.items():
        mm = re.match(r"dec_label_pc_([0-9a-f]+)$", lab2 or "")
        if mm:
            va2 = int(mm.group(1), 16)
            if va2 not in _REGION_VAS:      # 他 site の領域 block は出口にしない (再 lift 対象)
                reg.exit_vas.add(va2)
    reg.S_is_label = ix.has_label(S)
    if not reg.S_is_label:
        reg.exit_vas.discard(S)
    reg.live_at_S = _live_in_at(mf, S)
    reg.head_bi = cb
    reg.split_li = sp
    reg.tail_lines = list(tail_lines)
    reg.tail_range = set((cb, i) for i in range(sp, len(blk.lines)))
    # tail の新ラベル (S が既存ラベルならラベル衝突を避ける)
    if reg.S_is_label:
        tail_label = "dec_label_pc_p1tail_%x_%x" % (A, J)
    else:
        tail_label = "dec_label_pc_%x" % S
    # ---- 脱落側入口 D の IR ラベルが head block 自身 (= RetDec がマージした巨大 block の
    #      ラベルが末尾側の機械語 VA であるケース)。そのまま relay を作ると
    #      head → relay → head の自己辺になり processReplacing が停止しない (CAB-238 §6)。
    #      tail を D の機械語コードの始点で割り, 「生存側尾部」+「合流点」の 2 block に
    #      分け、脱落側は合流点ブロックへ直接渡す (機械語の jmp と同じ構造)。
    reg.join_label = None
    if ix.label_idx.get("dec_label_pc_%x" % D) == cb:
        ti = None
        for i, ln in enumerate(tail_lines):
            a = mod.addr_of(ln)
            if a is not None and a >= D:
                ti = i
                break
        if ti is None:
            raise Unsupported("join %x: head block label collision, split point が見つからない" % D)
        tail_lines = list(tail_lines)
        reg.join_label = "dec_label_pc_p1join_%x_%x" % (A, J)
        head_tail = tail_lines[:ti]
        reg.join_scan = list(tail_lines[ti:])   # emit_merge_stores が読む load 行
        # 合流点 (尾部の後半) が「生存側尾部 (前半) で定義した値」を読む場合, 脱落側経路では
        # その定義が実行されないので reg2mem マージ (pred ごとの store + 合流点 load) が要る。
        # 機械語レベルでは jcc の両辺が xmm0 等を別値にすることがあり, 正当な phi である。
        reg.join_merge = _plan_join_merge(mod, fn, mf, reg.join_scan, head_tail,
                                          reg.join_alloca_lines)
        if reg.join_merge is None:
            raise Unsupported("join %x: 合流点の入力レジスタを解決できない" % D)
        tail_lines = head_tail + ["  br label %%%s" % reg.join_label]
        reg.tail_lines = list(tail_lines)
        log.append("join split jcc@%x: D=%x を tail 内の合流点へ (tail %d 行 / join %d 行%s)"
                   % (J, D, ti, len(reg.join_scan),
                      " / merge %d" % len(reg.join_merge) if reg.join_merge else ""))
    st0 = {"__w": set(), "fl": ("site", None), "rsp": {}}
    dlabel = reg.run(D, st0)
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
    # 関数先頭 block は LLVM の entry (pred 禁止)。relay 等の新辺が先頭 block に
    # 向かっても壊れないよう, 常に新 entry block を先頭に置く (join alloca の配置先でもある)。
    e0 = fn.blocks[0]
    lab0 = "dec_label_pc_p1entry_%x_%x" % (A, J)
    fn.blocks.insert(0, IR.Block(lab0, lab0 + ":", list(reg.join_alloca_lines) + ["  br label %%%s" % e0.label]))
    tb = IR.Block(tail_label, tail_label + ":", tail_lines)
    fn.blocks.insert(cb + 1, tb)
    if reg.join_label:
        fn.blocks.append(IR.Block(reg.join_label, reg.join_label + ":", reg.join_scan))
    for (lab, lines) in reg.blocks:
        fn.blocks.append(IR.Block(lab, lab + ":", lines))
    stats["reconstructed"] = stats.get("reconstructed", 0) + 1
    for k, v in reg.vocab.items():
        stats["vocab_" + k] = stats.get("vocab_" + k, 0) + v
    log.append("reconstructed jcc@%x (survivor=%s %x, region blocks=%d)%s" % (
        J, "T" if S == T else "F", S, len(reg.blocks),
        (" vocab=" + ",".join("%s:%d" % kv for kv in sorted(reg.vocab.items()))) if reg.vocab else ""))
    return True


def _instr_type(s):
    """IR 命令文字列 (token 列) から結果の型を取り出す。取れなければ None。

    `%x = <ty> <op> ...` / `%x = call <ty> @f(...)` / `%x = load <ty>, ptr ...`
    / `%x = phi <ty> ...` 系に対応。call は `call` 自体が型ではないので op 後の型を採る。"""
    s = s.lstrip()
    m = re.match(r"^%[\w$.\-]+ = (call|invoke) (\S+)\s", s)
    if m:
        t = m.group(2).rstrip(",")
        return t if re.match(r"^(i\d+|ptr|float|double|void|<.*>|\{.*\}|\[.*\])$", t) else None
    m = re.match(r"^%[\w$.\-]+ = (\S+)\s", s)
    if not m:
        return None
    t = m.group(1).rstrip(",")
    if re.match(r"^(i\d+|ptr|float|double|void|<.*>|\{.*\}|\[.*\])$", t):
        return t
    return None


def _plan_join_merge(mod, fn, mf, join_lines, head_tail_lines, alloca_lines):
    """合流点 (join) が生存側尾部 (head_tail) で定義した値を読む時の reg2mem マージを計画する。

    戻り値: [(ir値, 型, alloca, レジスタ)] — 脱落側 relay はレジスタの到達値を store し,
    合流点は alloca を load して使う (RetDec の reg2mem イディオムと同じ)。
    解決できないレジスタが 1 つでもあれば None (呼出側が unsupported にする)。
    """
    defined = {}                       # ir 値 -> (型, 機械語 VA)
    for ln in head_tail_lines:
        s = IR.strip_tokens(ln)
        m = re.match(r"^\s*(%[\w$.\-]+) = ", s)
        if not m:
            continue
        ty = _instr_type(s)
        if ty is None or ty == "void":
            continue
        defined[m.group(1)] = (ty, mod.addr_of(ln))
    if not defined:
        return []
    need = {}
    for ln in join_lines:
        s = IR.strip_tokens(ln)
        head = s.split(" = ")[0]
        for u in set(re.findall(r"%[\w$.\-]+", s)):
            if u in defined and u != head:
                need[u] = defined[u]
    if not need:
        return []
    out = []
    for u, (ty, va) in sorted(need.items()):
        reg = None
        if va is not None:
            it = mf.insns.get(va)
            if it is not None:
                cand = sorted(r for r in it.writes
                              if r.startswith("xmm") or (r.startswith("r") and r != "rsp"))
                if len(cand) == 1:
                    reg = cand[0]
        if reg is None:
            return None                       # レジスタ対応が取えない値は諮める
        n0 = 0
        while True:
            a = "%%p1jm_%x_%d" % (va, n0)
            if a not in alloca_lines and a not in [m[2] for m in out]:
                break
            n0 += 1
        alloca_lines.append("  %s = alloca %s" % (a, ty))
        alloca_lines.append("  store %s 0, ptr %s" % (ty, a))
        # 生存側尾部 (FALSE 側) の終端 = この値の store (後続の br label %join の前)
        head_tail_lines.append("  store %s %s, ptr %s" % (ty, u, a))
        nv = "%%p1jmv_%x_%d" % (va, n0)
        join_lines.insert(0, "  %s = load %s, ptr %s" % (nv, ty, a))
        for i, ln in enumerate(join_lines):
            if i == 0:
                continue
            join_lines[i] = re.sub(r"(?<![\w$.])" + re.escape(u) + r"(?![\w$.])", nv, ln)
        out.append((u, ty, a, reg))
    return out


def _all_blocks_live_in(mf):
    """全機械語 block 開始点の live-in (_live_in_at の block 単位版, 1 fixpoint)。"""
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
    return LIVE


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


def _renumber_fn(fn):
    """関数内の無名番号 (値 %N と無名 block は同じ 0 起点の番号空間を共有する) を
    file 順で引き直す (LIFTLIB-2)。

    LLVM の構文規則で関数内の番号は単調増加が必要。head block の tail 分割と挿入に
    より RetDec の元番号の file 順が崩れる事があるため, 変更のあった関数を引き直す。
    無名 block の `; <label>:N:` 行と `label %N` 参照も同じ番号空間なので一緒に張替える。
    番号の対応は写像置換なので意味は不変 (use/def の構造はそのまま)。"""
    items = []                            # file 順の (種別, 旧番号)
    for b in fn.blocks:
        for ln in b.lines:
            m = re.match(r"^; <label>:(\d+):", ln)
            if m:
                items.append(int(m.group(1)))
                continue
            m = re.match(r"^\s*%(\d+) = ", ln)
            if m:
                items.append(int(m.group(1)))
    if not items:
        return 0
    mapping = {old: n for n, old in enumerate(items)}
    pat = re.compile(r"(?<![\w$.!\-])%(\d+)(?![\w$.!\-])")
    labpat = re.compile(r"(^; <label>:)(\d+):")

    def sub(ln):
        s = labpat.sub(lambda m: "%s%d:" % (m.group(1), mapping[int(m.group(2))])
                       if int(m.group(2)) in mapping else m.group(0), ln)
        return pat.sub(lambda m: "%%%d" % mapping[int(m.group(1))]
                       if int(m.group(1)) in mapping else m.group(0), s)

    for b in fn.blocks:
        b.lines = [sub(l) for l in b.lines]
        if b.header:
            b.header = sub(b.header)
    return len(items)


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
    _REGION_VAS.clear()          # 領域 block の請求は関数単位 (LIFTLIB-2)
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
    if repair and (stats.get("reconstructed") or stats.get("rewired")):
        stats["renumbered"] = _renumber_fn(fn)
    return stats
