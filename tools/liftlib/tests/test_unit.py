#!/usr/bin/env python3
"""tests/test_unit.py — liftlib の軽量ユニット/性質テスト (python3 tests/test_unit.py; 約 20 秒)。

  T1 base 正規化が元チェーン (m2+m5) の出力と一致 (FA/KH/OTT の raw .ll)
  T2 p1_legacy / shift / gdata_legacy が OTT 元チェーンの中間成果物と一致
  T3 SIMD 生成が RetDec の接尾番号 (`__N`) に依存しない (接尾を付け替えても生成 C が同一)
  T4 同じ名前でも署名が違えば別 helper になる (FA の mulss(i128,i32) と OTT の mulss(i128,i128))
  T5 mnemonic 被覆: KH census 205 種のうち未被覆 0 (pcmpistri / vinsertf128 は LIFTLIB #241 で被覆)
  T6 機械語解析: FA gain の live-in / 到達定義
  (全テストを実行し, 失敗は最後に一覧表示する。終了コードは失敗があれば非 0)
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
T = os.path.join(HERE, "..", "..")

from liftlib import ir as IR                       # noqa: E402
from liftlib import lb_layout, runtime_lb          # noqa: E402
from liftlib.passes import base, dataimage, p1_legacy, remap  # noqa: E402
from liftlib.simd import gen                       # noqa: E402
from liftlib.pe import Image                       # noqa: E402
from liftlib.mc import MFunc                       # noqa: E402

FA_PE = os.path.join(T, "targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64")
from liftlib.env import OTT_DLL                    # noqa: E402
DUP = ("declare i64 @function_1803ded20", "declare i64 @function_18004cf20")


def nb(t):
    return [l for l in t.split("\n") if l.strip()]


def repmap_delta(new, ref):
    """#3067 の修正前参照 (tools/m6/work/ir7e_p*.ll) との差分行数を返す。差分は repmap の書換えだけであること:
    comis 直後の分岐 (`br i1 %<旧名>.reload` → `%pcNcf/zf`) と or 1 行 (2 組) の計 18 行。旧名と新名以外は一致する。
    参照は work/ のみの修正前出力 (commit 不可) で, R2 (work-m6-ott) を再投入するまで据え置く。再投入後は `==` の比較に戻す。"""
    a, b = new.split("\n"), ref.split("\n")
    assert len(a) == len(b), (len(a), len(b))
    d = [(x, y) for x, y in zip(a, b) if x != y]
    for x, y in d:
        assert re.sub(r"%pc\d+(?:cf|zf|pf)\b", "%F", x) == re.sub(r"%(?:cf|zf|pf)\.\d+\.reload\b", "%F", y), (x, y)
    return len(d)


def t1():
    text, _ = base.run_base(open(os.path.join(T, "m6/work/ott.drc.ll")).read(), base.make_args())
    assert nb(IR.Module.parse(text).dump(strip=True)) == nb(open(os.path.join(T, "m6/work/ott_lift.ll")).read())
    for raw, ref in [("targets/freshair/work/lift_gain/gain.drc.ll", "targets/freshair/work/lift_gain/gain_lift.ll"),
                     ("targets/kilohearts/poc_gain/work/gain.drc.ll", "targets/kilohearts/poc_gain/work/gain_lift.ll")]:
        if not os.path.exists(os.path.join(T, raw)):
            continue
        text, _ = base.run_base(open(os.path.join(T, raw)).read(), base.make_args())
        out = [l for l in nb(IR.Module.parse(text).dump(strip=True)) if not l.startswith(DUP)]
        r = [l for l in nb(open(os.path.join(T, ref)).read()) if not l.startswith(DUP)]
        assert out == r, raw     # 差は重複 declare の除去だけ (元チェーンでは後段 pass が除去)
    print("T1 ok (base == m2+m5)")


def t2():
    """T2: p1_legacy/shift/gdata の段別出力を m6 の参照鎖と比べる。
    参照 (ir7e_p1/p2/p3.ll) は #3067 修正前の出力 (work/ のみ・commit 不可)。修正で変わるのは repmap の 18 行だけ (repmap_delta)。
    R2 (work-m6-ott) 再投入で参照が修正後になったら, 下の repmap_delta(...) == 18 を `o == ref` の完全一致に戻す。"""
    M6 = os.path.join(T, "m6/work")
    o, st = p1_legacy.legacy_p1(open(os.path.join(M6, "ott_lift.ll")).read())
    assert repmap_delta(o, open(os.path.join(M6, "ir7e_p1.ll")).read()) == 18
    o2, n = remap.shift_va(o)
    assert repmap_delta(o2, open(os.path.join(M6, "ir7e_p2.ll")).read()) == 18
    o3, gst = remap.gdata_legacy(o2, Image(OTT_DLL))
    assert repmap_delta(o3, open(os.path.join(M6, "ir7e_p3.ll")).read()) == 18
    print("T2 ok (p1_legacy/shift/gdata == m6 chain, 修正前参照との差は repmap 18 行のみ; p1 inserts=%d shift=%d gdata=%d)" % (st["inserted"], n, gst["replaced"]))


def t3():
    text = open(os.path.join(T, "m6/work/ott_shift3b.ll")).read()
    d0 = gen.scan_decls(text)
    c0 = gen.emit_c(d0, use_names="canon")[0]
    uniq = {}
    for d in d0:
        uniq[d.name] = "%s__%d" % (gen.SUFFIX_RE.sub("", d.name), 1000 + len(uniq))
    t2_ = re.sub(r"@(__asm_[\w.\-]+)", lambda m: "@" + uniq.get(m.group(1), m.group(1)), text)
    c1 = gen.emit_c(gen.scan_decls(t2_), use_names="canon")[0]
    key = lambda c: sorted(l for l in c.split("\n") if l.startswith("LL_EXPORT"))
    assert key(c0) == key(c1) and len(key(c0)) > 100
    print("T3 ok (helper 生成は接尾番号に依存しない: %d helpers)" % len(key(c0)))


def t4():
    fa_src = os.path.join(T, "targets/freshair/work/lift_gain/gain_lift.ll")
    if not os.path.exists(fa_src):    # 旧 FA 中間成果物が無い環境 (Actions) は liftlib 自前の RetDec 生出力 (同じ __asm_mulss 宣言) を使う
        fa_src = os.path.join(T, "liftlib/work/fa_gain/fa_gain.drc.ll")
    fa = gen.scan_decls(open(fa_src).read())
    ott = gen.scan_decls(open(os.path.join(T, "m6/work/ott_shift3b.ll")).read())
    fm = {d.name: d.sig for d in fa if d.base == "mulss"}
    om = {d.name: d.sig for d in ott if d.base == "mulss"}
    assert fm["__asm_mulss"] != om["__asm_mulss"]                 # 同名でも署名が違う
    assert len({d.canon for d in fa + ott if d.base == "mulss"}) == 2
    print("T4 ok (同名 mulss でも署名で別 helper: FA %s / OTT %s)" % (fm["__asm_mulss"], om["__asm_mulss"]))


def t5():
    d = json.load(open(os.path.join(HERE, "..", "data/kh_mnemonics.json")))
    allm = sorted(set(d["effects"]) | set(d["infra"]) | set(d["hosts"]))
    cov, unc = gen.coverage(allm)
    assert unc == [], unc
    print("T5 ok (mnemonic %d 種中 未被覆 %s)" % (len(allm), unc))


def t6():
    img = Image(FA_PE)
    mf = MFunc(img, *img.func_at(0x180afe090))
    assert {"rcx", "rdx"} <= mf.live_in()
    assert mf.defs_before(0x180afe112, "xmm1") == {0x180afe0b1, 0x180afe0b7}
    assert "xmm1" in MFunc(img, *img.func_at(0x180afe3a0)).live_in()
    print("T6 ok (mc: live-in / reaching defs)")


def t7():
    """dataimage の DIR64 補正は「元値側の image 範囲」判定 (CAB-220)。
    旧実装の `0x400000 <= nt` は LB_BASE<0x400000 で補正を黙って落としていた。"""
    img = Image(OTT_DLL)
    dc, cnt = dataimage.gen_data_c(img, va_base=0x10000)
    blob = re.search(r"dlld__rdata\[\] = \{\n(.*?)\n\};", dc, re.S).group(1)
    got = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})\b", blob))
    lo, sd = next((lo, d) for n, lo, d in dataimage.sections_raw(img) if n == ".rdata")
    nfix = nlow = 0
    for r in img.relocs_dir64():
        if lo <= r <= lo + len(sd) - 8:  # #593: dataimage と同じ境界 (末尾 8B slot を含む)
            off = r - lo
            v = struct.unpack_from("<Q", sd, off)[0]
            if img.base <= v < img.base + img.size:      # image 内ポインタ = 補正対象
                assert got[off:off + 8] == struct.pack("<Q", v - img.base + 0x10000), hex(r)
                nfix += 1
                nlow += v < img.base + 0x400000 - 0x10000  # 補正後 nt<0x400000 = 旧フィルタの漏れ分
    assert nfix == cnt[".rdata"] and nlow > 1000, (nfix, cnt, nlow)
    c0 = dataimage.gen_data_c(img, va_base=0x30000000)[1]
    c1 = dataimage.gen_data_c(img, va_base=0x1230000)[1]
    assert cnt == c0 == c1, (cnt, c0, c1)            # 補正数は base 非依存 (旧フィルタでは base 依存)
    print("T7 ok (dataimage: DIR64 補正 %d 件 = base 非依存, うち nt<0x400000 %d 件は旧フィルタの漏れ分)" % (nfix, nlow))


def t8():
    """lb_layout (liftlib 取り込み版) が lowbase 正本 (tools/hostbridge/lowbase/lb_layout.py) と同一。"""
    ref_path = os.path.join(T, "hostbridge/lowbase/lb_layout.py")
    if not os.path.exists(ref_path):
        print("T8 skip (lowbase/lb_layout.py 無し)")
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("lb_layout_ref", ref_path)
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    for args in ((0x10000, 0x308000, 0x100000, 16, 64), (0x1230000, 0x308000, 0x100000, 24, 64),
                 (0x400000, 0x18c0000, 0x120000, 32, 64)):
        assert lb_layout.layout(*args) == ref.layout(*args), args
    try:
        lb_layout.layout(base=0x8000)                # 64KiB 境界 assert
        raise SystemExit("T8: 64KiB 未満の base が通ってしまった")
    except AssertionError:
        pass
    print("T8 ok (lb_layout == lowbase 正本: OTT@0x10000 arena=%s)" % hex(lb_layout.layout(0x10000)["LB_ARENA"]))


def t9():
    """runtime_lb: C ランタイムのマクロ化が既定値で元ソースと等価 (CAB-220)。"""
    paths = {"m6_rt.c": os.path.join(T, "m6/m6_rt.c"), "m8_rt.c": os.path.join(T, "m8/m8_rt.c"),
             "m10_boot.c": os.path.join(T, "m10/m10_boot.c"),
             "m6_stubs_hand.c": os.path.join(T, "m6/work/m6_stubs_hand.c")}
    paths = {k: v for k, v in paths.items() if os.path.exists(v)}
    if "m6_rt.c" not in paths:
        print("T9 skip (m6/m8/m10 の C ランタイム無し)")
        return
    outs, rep = runtime_lb.emit(paths, os.path.join(HERE, "..", "work", "rt_lb_test"))
    assert runtime_lb.audit_summary(rep) == {"m6_rt.c": 2, "m8_rt.c": 2, "m6_stubs_hand.c": 4, "m10_boot.c": 1}, rep
    # 既定 (-D 無し) でマクロ展開すると元の固定値になる (前処理: clang が無いので #ifndef 既定の存在で判定)
    t8c = open(outs["m8_rt.c"]).read()
    assert "#define LB_IMG_BASE 0x30000000ul" in t8c and "a < LB_MAX_MEM" in t8c
    t10c = open(outs["m10_boot.c"]).read()
    assert "static volatile uint32_t lb_mscr[4096];" in t10c and "#define MSCR ((volatile" not in t10c
    print("T9 ok (runtime_lb: m6_rt=2 m8_rt=2 stubs_hand=4 m10_boot=1 置換, LB_IMG_BASE/LB_MAX_MEM マクロ化)")


def t10():
    """CAB-239: mini-lifter 語彙拡張 — OTT 生 IR で落下分岐の再構成数と新語彙の発動を実測値で固定。"""
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T10 skip (OTT raw .ll 無し)")
        return
    from liftlib.passes import p1
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    log, st = [], {}
    for fn in mod.funcs():
        va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
        if va is None or img.func_at(va) is None:
            continue
        p1.run_function(mod, fn, img, True, log, st)
    # 実測固定 (CAB-239): 再構成 18 以上 / UNSUPPORTED 31 以下 / 新語彙 (rot/int_jcc/call/rsp) の発動
    assert st.get("reconstructed", 0) >= 19, st
    assert st.get("unsupported", 0) <= 30, st
    assert st.get("rewired", 0) >= 30, st
    assert st.get("vocab_rot", 0) >= 2 and st.get("vocab_int_jcc", 0) >= 2, st
    assert st.get("vocab_call", 0) >= 3, st
    print("T10 ok (p1 語彙拡張: reconstructed=%d unsupported=%d rewired=%d vocab_call=%d rot=%d int_jcc=%d)"
          % (st.get("reconstructed", 0), st.get("unsupported", 0), st.get("rewired", 0),
             st.get("vocab_call", 0), st.get("vocab_rot", 0), st.get("vocab_int_jcc", 0)))


def t11():
    """CAB-239: leafabi — exp (0-arg i64) の ret を xmm0 bits 戻りに差し替え, gdata pad が表 base を拡張。"""
    from liftlib.passes import leafabi
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw) or not os.path.exists(OTT_DLL):
        print("T11 skip (OTT の成果物無し)")
        return
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    fn = mod.func("function_1801b4220")
    mf = MFunc(img, *img.func_at(0x1801b4220))
    from liftlib.regbind import Binder
    st, lg = {}, []
    leafabi._ret_thread(mod, fn, mf, Binder(mod, fn, mf), lg, st)
    rets = [l for l in fn.render() if l.strip().startswith("ret")]
    threaded = [l for l in rets if "%lf_" in l]
    assert len(threaded) >= 6, threaded[:4]
    assert st.get("ret_threaded", 0) >= 6, st
    # gdata pad: 表 base (ptrtoint 被参照) が次 global VA まで拡張される
    text2, _ = base.run_base(open(raw).read(), base.make_args())
    mod2 = IR.Module.parse(text2)
    gst = remap.gdata(mod2, img, mode="all", base=img.base, pad_gap=True)
    tbl = [it for it in mod2.items if isinstance(it, str) and it.startswith("@global_var_18021fe80 = ")][0]
    m = re.search(r"\[(\d+) x i8\]", tbl)
    assert m and int(m.group(1)) > 8, tbl[:80]
    print("T11 ok (leafabi ret_threaded=%d, gdata pad: 表 base %d bytes)" % (st.get("ret_threaded", 0), int(m.group(1))))


def t12():
    """LIFTLIB-2 (CAB-256): 領域 DAG 化 + join split/merge で OTT の再構成数と語彙発動を実測値で固定。

    CAB-239 時点 (reconstructed 19 / unsupported 30) から, 領域内合流 (DAG) の reg2mem phi 合成と
    非支配 bind 値のフォールバックで **再構成 25 / 残留 21** に改善する。
    同時に CAB-238 6 の無限ループ要因 (脱落側入口が head block 自身 = 自己辺) を
    join split で解消する site (18011ffdd / 18012024b) の存在も固定する。"""
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T12 skip (OTT raw .ll 無し)")
        return
    from liftlib.passes import p1
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    log, st = [], {}
    for fn in mod.funcs():
        va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
        if va is None or img.func_at(va) is None:
            continue
        p1.run_function(mod, fn, img, True, log, st)
    # 実測固定 (LIFTLIB-2): 再構成 25 以上 / UNSUPPORTED 21 以下 / DAG 語彙 (phi_join)
    # LIFTLIB-4: 未使用 vocab (join_merge_store / join split) への依存は外す。
    #   _value_ok の領域値支配判定を修正したことで, 脱落側入口 D が head block 自身の
    #   ラベルになる site (18011ffdd / 18012024b) は join split ではなく DAG 側で
    #   扱えるようになった。重要なのは **性質** (自己辺が無い = 無限ループしない) なので
    #   そちらを assert する。
    assert st.get("reconstructed", 0) >= 25, st
    assert st.get("unsupported", 0) <= 21, st
    assert st.get("vocab_phi_join", 0) >= 1, st          # 領域内合流の phi 合成
    # CAB-238 6 の性質: 自己辺 (br label %自分自身) が 1 本も無いこと。
    # join split が発動していればそれも読む (情報目的)。
    split = [l for l in log if "join split" in l]
    self_edges = 0
    for fn in mod.funcs():
        for b in fn.blocks:
            for ln in b.lines:
                m2 = re.match(r"^\s*br label %([\w$.\-]+)", IR.strip_tokens(ln))
                if m2 and m2.group(1) == b.label:
                    self_edges += 1
    assert self_edges == 0, "自己辺 %d 本 (CAB-238 6 の無限ループ)" % self_edges
    print("T12 ok (DAG/phi: reconstructed=%d unsupported=%d phi_join=%d join_merge=%d join_split=%d self_edges=%d)"
          % (st.get("reconstructed", 0), st.get("unsupported", 0),
             st.get("vocab_phi_join", 0), st.get("vocab_join_merge_store", 0), len(split), self_edges))


def t13():
    """[LIFTLIB-3] f2 callee 相 → p1 で dropped 領域の `bind xmm0/xmm1` が解ける事を固定。

    LIFTLIB-2 時点 (f2 無し) の残留は 21 (bind xmm0 6 / bind xmm1 5 / ...)。CRT leaf が
    入口 xmm を読むのに IR 側に値が無いのが原因なので, f2 の callee 相 (%xmmK_bits 引数の
    付与) を先に流すと bind が成功する。数え方: dbg_reason.py と同じく p1.run_function の
    UNSUPPORTED 行を理由で集計する。
    """
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T13 skip (OTT raw .ll 無し)")
        return
    import collections
    from liftlib.passes import p1, f2
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    log = []
    st = {}
    f2.run(mod, img, log, st, phase="callee")          # LIFTLIB-3: 入口 xmm 引数化を先に
    log2 = []
    for fn in mod.funcs():
        va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
        if va is None or img.func_at(va) is None:
            continue
        p1.run_function(mod, fn, img, True, log2, st)
    cnt = collections.Counter()
    for l in log2:
        if l.startswith("UNSUPPORTED"):
            r = l.split(": ", 1)[1]
            r = re.sub(r"@[0-9a-f]+", "@X", r)
            r = re.sub(r"%[^\s]+", "%V", r)
            cnt[r] += 1
    # 実測固定: LIFTLIB-3 で 15 以下, LIFTLIB-4 で **6 以下** (bind xmm0 1 → 0)
    assert st.get("unsupported", 0) <= 6, st
    assert cnt.get("bind xmm0 @X", 0) <= 0, cnt
    print("T13 ok (f2 callee → p1: unsupported=%d 再構成=%d bind_xmm0=%d bind_xmm1=%d)"
          % (st.get("unsupported", 0), st.get("reconstructed", 0),
             cnt.get("bind xmm0 @X", 0), cnt.get("bind xmm1 @X", 0)))
    # LIFTLIB-4: 領域値の支配判定と原本優先の効果 (bind xmm1 5 → 1, merge 系 4+2 → 0)
    assert cnt.get("bind xmm1 @X", 0) <= 1, cnt


def t14():
    """[LIFTLIB-3] 汎用 xmm0-ret bind の検出と leafabi 自動拡張を固定。

    xmm0_ret_census.py と同じ母集合 (leaf module の function define) で
    ret_in_xmm0() を数え, 別アルゴリズム (ENTRY→ret の未書経路の非存在) と一致する事を
    確認する。さらに tan 0x1801a9be0 → function_1801aa1a0 (tan の kernel) が検出される事
    (cfg の ret_xmm0 明示リストに無い = 漏れていた callee) を固定する。
    """
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T14 skip (OTT raw .ll 無し)")
        return
    from liftlib.mc import MFunc
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    hit, alt = [], []
    for fn in mod.funcs():
        nm = fn.name
        if not re.match(r"function_[0-9a-f]+$", nm):
            continue
        va = int(nm.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        mf = MFunc(img, *rng)
        if mf.ret_in_xmm0():
            hit.append(nm)
        # 別アルゴリズム: ENTRY→ret の未書経路が無い事
        cfg = mf.cfg()
        rets = set(v for v in mf.order if mf.insns[v].is_ret)
        if not rets:
            continue
        seen, todo, bad = set(), [(mf.start, False)], False
        while todo and not bad:
            blk, wrote = todo.pop()
            if (blk, wrote) in seen:
                continue
            seen.add((blk, wrote))
            w = wrote
            for v in cfg[blk]["vas"]:
                if v in rets and not w:
                    bad = True
                    break
                if "xmm0" in mf.insns[v].writes:
                    w = True
            if bad:
                break
            for sc in cfg[blk]["succ"]:
                todo.append((sc, w))
        if not bad:
            alt.append(nm)
    assert set(hit) == set(alt), "検出不一致: %s" % sorted(set(hit) ^ set(alt))
    assert len(hit) >= 100, "検出数が少なすぎる: %d" % len(hit)
    # tan の kernel は cfg の ret_xmm0 明示リストに無い (従来の漏れ)
    assert "function_1801aa1a0" in hit, "tan kernel が未検出"
    print("T14 ok (xmm0-ret 検出 %d 関数, 別アルゴリズムと一致, tan kernel 検出)" % len(hit))


def t15():
    """[LIFTLIB-4] 領域値の支配判定修正 + 原本優先 bind の効果を固定。

    LIFTLIB-4 (CAB-272) の 2 つの修正:
      1. `Region._value_ok` が領域値の名前に埋めた VA を「値の機械語 VA」と誤認していた
         (あれはタグ。relay は他所の VA をタグに使う)。`self.vdb` (定義 block) で
         判定するようにした → merge 系の誤 FAIL が消える。
      2. `regbind.value_defined_at` が同一アドレスの IR 命令の**末尾** (領域側) を
         拾っていたため, 別領域の経路固有 SSA を参照して非支配になっていた。原本を
         優先するようにした → bind xmm1 が解ける。

    効果 (f2 callee + p1, dbg_reason_f2.py と同条件): 残留 15 → **6**。
    ネガティブコントロール (規則 41) も同時に固定する。
    """
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T15 skip (OTT raw .ll 無し)")
        return
    import collections
    import subprocess
    from liftlib.passes import p1, f2
    img = Image(OTT_DLL)

    def run(env=None):
        text, _ = base.run_base(open(raw).read(), base.make_args())
        mod = IR.Module.parse(text)
        f2.run(mod, img, [], {}, phase="callee")
        log, st = [], {}
        for fn in mod.funcs():
            va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
            if va is None or img.func_at(va) is None:
                continue
            p1.run_function(mod, fn, img, True, log, st)
        cnt = collections.Counter()
        for l in log:
            if l.startswith("UNSUPPORTED"):
                r = l.split(": ", 1)[1]
                r = re.sub(r"@[0-9a-f]+", "@X", r)
                r = re.sub(r"%[^\s]+", "%V", r)
                cnt[r] += 1
        return st, cnt

    HERE = os.path.dirname(os.path.abspath(__file__))
    # 再計算スクリプトは必ずコミット済みの物を使う (規則 37)。work/ 配下の開発用
    # スクリプトに依存すると clean HEAD で再現できない (LIFTLIB-4 で実測)。
    dbg = os.path.join(HERE, "..", "p1_residual_census.py")

    def run_env(extra):
        e = dict(os.environ, **extra)
        r = subprocess.run([sys.executable, os.path.abspath(dbg), "--json"], capture_output=True,
                           text=True, env=e, timeout=1800)
        assert r.returncode == 0, r.stderr[-500:]
        return json.loads(r.stdout)["stats"]

    st0, cnt0 = run()
    # LIFTLIB-4 実測固定: 残留 6 以下 / bind xmm0 0 / bind xmm1 1以下 / merge xmm2 0
    assert st0.get("unsupported", 99) <= 6, st0
    assert cnt0.get("bind xmm0 @X", 0) <= 0, cnt0
    assert cnt0.get("bind xmm1 @X", 0) <= 1, cnt0
    assert cnt0.get("merge xmm2 @X", 0) == 0, cnt0
    # ネガコン 1: 原本優先を止めると bind xmm1 が 1 → 4 に戻る (残留 6 → 9)
    st1 = run_env({"LL_NO_ORIG_PREF": "1"})
    assert st1["unsupported"] > st0["unsupported"], (st1, st0)
    assert st1["unsupported"] <= 9, st1
    # ネガコン 2: vdb 支配判定を止めると merge 系が 0 → 6 に戻る (残留 6 → 13)
    st2 = run_env({"LL_NO_VDB_DOM": "1"})
    assert st2["unsupported"] > st0["unsupported"], (st2, st0)
    assert st2["unsupported"] <= 14, st2
    # 両方を止めると LIFTLIB-4 着手前 (15) に戻る
    st3 = run_env({"LL_NO_ORIG_PREF": "1", "LL_NO_VDB_DOM": "1"})
    assert st3["unsupported"] == 15, st3
    print("T15 ok (LIFTLIB-4: unsupported 6, orig優先OFF %d, vdb支配OFF %d, 両OFF %d)"
          % (st1["unsupported"], st2["unsupported"], st3["unsupported"]))


def t16():
    """[HB-H3 / #93] iargs: 整数引数 (rdx/r8/r9) 脱落の機械検出と復元 (OTT, RetDec raw .ll)。

    - 検出: AudioEffect ctor の委譲 (function_180127550 は rcx のみ, 機械語は r8/r9 まで素通し) を含む
      define 15 / call site 15 を検出する (実測値)。
    - 復元: 復元後は再走査で 0 / 0。ctor の呼出しが (this, audioMaster, 1, 20) になる。
    - 冪等: 2 回流しても変化なし。
    """
    raw = os.path.join(T, "m6/work/ott.drc.ll")
    if not os.path.exists(raw):
        print("T16 skip (OTT raw .ll 無し)")
        return
    from liftlib.passes import iargs
    img = Image(OTT_DLL)
    text, _ = base.run_base(open(raw).read(), base.make_args())
    mod = IR.Module.parse(text)
    pre = iargs.scan(mod, img)
    assert len(pre["define_short"]) == 15 and len(pre["sites_short"]) == 15, (len(pre["define_short"]), len(pre["sites_short"]))
    assert ("function_180127550", 1, 4) in pre["define_short"], pre["define_short"]
    # sites_entry: 引数の個数は足りているが入口値素通し位置に別値 (undef 等) を渡している site (実測 17)
    assert len(pre["sites_entry"]) == 17, len(pre["sites_entry"])
    assert ("function_180127550", 0x180127559, "function_180126920", 1) in pre["sites_entry"], pre["sites_entry"]
    st, lg = {}, []
    iargs.run(mod, img, lg, st)
    # HB-H25 (#1158) で 5 番目の引数 (入口 rsp+0x28) を読む 2 site (1801c162b / 1801c1752) も bind 済みのため unbound は 0
    assert st.get("site_unbound", 0) == 0, st
    assert not [l for l in lg if "unbound" in l], lg
    post = iargs.scan(mod, img)
    assert not post["define_short"] and not post["sites_short"] and not post["sites_entry"], post
    ctor = [l for l in mod.func("function_18011d400").blocks[0].lines if "@function_180127550(" in l]
    assert len(ctor) == 1 and "(i64 %arg1, i64 %arg2, i64 1, i64 20)" in ctor[0], ctor
    # movzx edx,dl 合成 (site 1801a3117): rdx を入口 dl の 0 拡張として bind する (unbound にならない)
    assert not any("1801a3117" in l and "unbound" in l for l in lg), [l for l in lg if "1801a3117" in l]
    assert any("function_1801a30b0@1801a3117" in l and "%ia_1801a3117_1z" in l for l in lg), lg
    # 復元済みの site の rcx (入口素通し) を undef に戻すと detect-only が検出する (逆方向の被覆)
    fn = mod.func("function_18011d400")
    li = next(i for i, l in enumerate(fn.blocks[0].lines) if "@function_180127550(" in l)
    good = fn.blocks[0].lines[li]
    fn.blocks[0].lines[li] = good.replace("(i64 %arg1, ", "(i64 undef, ", 1)
    assert fn.blocks[0].lines[li] != good
    bad = iargs.scan(mod, img)
    assert [s for s in bad["sites_entry"] if s[0] == "function_18011d400" and s[2] == "function_180127550" and s[3] == 0], bad["sites_entry"]
    fn.blocks[0].lines[li] = good
    assert not iargs.scan(mod, img)["sites_entry"]
    st2, lg2 = {}, []
    iargs.run(mod, img, lg2, st2)
    assert not st2.get("define_fixed") and not st2.get("sites_fixed"), st2
    print("T16 ok (iargs: define %d / site %d / entry %d 検出 → 復元 define_fixed=%d sites_fixed=%d site_unbound=%d, 再走査 0/0/0, 冪等)"
          % (len(pre["define_short"]), len(pre["sites_short"]), len(pre["sites_entry"]), st["define_fixed"], st["sites_fixed"], st.get("site_unbound", 0)))


def t16b():
    """[#898 review] movzx の高バイト (dh) は _canon_reg で dl と同じ族に正規化されるため合成してはならない (unbound)。
    movzx edx,dl は従来どおり合成する (下位 8 bit の 0 拡張)。"""
    from liftlib.mc import decode_one
    from liftlib.passes.iargs import _resolve

    class _B:
        def bind(self, reg, C):
            return ("%%src_%s" % reg, "i64") if C == 0x1000 else None

        def root_def(self, reg, C):
            return ("def", 0x1000, reg)

    class _MF:
        def __init__(self, it):
            self.insns = {0x1000: it}

    out = {}
    for txt, code in (("movzx edx, dh", b"\x0f\xb6\xd6"), ("movzx edx, dl", b"\x0f\xb6\xd2")):
        it = decode_one(code, 0x1000)
        assert it is not None and it.mnem == "movzx", (txt, it)
        ins = []
        out[txt] = _resolve(_B(), _MF(it), None, "rdx", 0x1010, "", "n", ins)
    assert out["movzx edx, dh"] is None, out
    assert out["movzx edx, dl"] is not None and out["movzx edx, dl"][1] == "i32", out
    print("T16b ok (movzx edx,dh は unbound / movzx edx,dl は 0 拡張で bind)")


def t16c():
    """[#2861] rip 相対 lea の定数アドレスは絶対 VA を即値で返す。32bit lea は下位 32bit に切り詰める。
    lea r8, [rip+16] @0x120000000 → 0x120000017 (i64)、lea r8d, [rip+16] → 0x20000017 (i32)。"""
    from liftlib.mc import decode_one
    from liftlib.passes.iargs import _resolve

    class _B:
        def bind(self, reg, C):
            return None

        def root_def(self, reg, C):
            return ("def", 0x1000, reg)

    class _MF:
        def __init__(self, it):
            self.insns = {0x1000: it}

    cases = (
        ("lea r8, [rip+16]", b"\x4c\x8d\x05\x10\x00\x00\x00", "r8", 0x120000017, "i64"),
        ("lea r8d, [rip+16]", b"\x44\x8d\x05\x10\x00\x00\x00", "r8", 0x20000017, "i32"),
    )
    for txt, code, reg, want, ty in cases:
        it = decode_one(code, 0x120000000)
        assert it is not None and it.mnem == "lea" and it.mem["base"] == "rip", (txt, it)
        ins = []
        got = _resolve(_B(), _MF(it), None, reg, 0x1010, "", "n", ins)
        assert got == (str(want), ty), (txt, got)
        assert ins == [], (txt, ins)
    print("T16c ok (rip lea は絶対 VA を即値で返す / 32bit は下位 32bit に切り詰め)")


def t17():
    """[LIFTLIB #241] i256 ABI + pcmpistri + F2 xmm 戻り搬送。
    (a) gen.py が i256 形を u64×4 平坦化 / Y 戻りで生成し, 実体 (kernels) を持つ (stub でない)
    (b) pcmpistri (void / i32 形) が生成される
    (c) F2 xmm 戻り: LL_XRET_LL (RetDec raw .ll) と LL_XRET_DLL (OTT_x64.dll) があれば検出→修復→再検出 + 注入評価を固定"""
    ll = ("declare i256 @__asm_vinsertf128(i256, i128, i8)\ndeclare void @__asm_vmovaps__3(i256, i256)\n"
          "declare void @__asm_vpcmpistri(i128, i128, i8)\ndeclare i32 @__asm_pcmpistri__2(i128, i128, i8)\n")
    c, rep = gen.emit_c(gen.scan_decls(ll), use_names="canon")
    assert not rep["unsupported"], rep["unsupported"]
    assert "Y __asm_vinsertf128__yyxb(u64 p0_0, u64 p0_1, u64 p0_2, u64 p0_3, u128 p1, u8 p2)" in c, c
    assert "__builtin_trap" not in c and "ll_pcmpistr_ecx" in c
    print("T17a ok (i256 ABI: u64x4 平坦化 + Y 戻り / pcmpistri void,i32 形とも生成)")
    xl, xd = os.environ.get("LL_XRET_LL"), os.environ.get("LL_XRET_DLL")
    if not (xl and xd and os.path.exists(xl) and os.path.exists(xd)):
        print("T17b skip (LL_XRET_LL / LL_XRET_DLL 未設定)")
        return
    from liftlib import inject
    from liftlib.passes import f2
    img = Image(xd)
    text, _ = base.run_base(open(xl).read(), base.make_args())
    mod = IR.Module.parse(text)
    st = {}
    f2.run_xmm_ret(mod, img, [], st, repair=True)
    assert st["xret_callees_pending"] == 3 and st["xret_rets_pending"] == 11, st
    assert st["xret_threaded"] == 9 and st["xret_rets_after"] == 2, st
    ev = inject.eval_f2_xret(mod, img)
    assert ev["injected"] == 9 and ev["detected"] == 9, ev
    print("T17b ok (F2 xmm 戻り: 検出 %d callee/%d ret → 搬送 %d → 残 %d, 注入 %d/%d 検出)"
          % (st["xret_callees_pending"], st["xret_rets_pending"], st["xret_threaded"], st["xret_rets_after"], ev["detected"], ev["injected"]))


def t18():
    """[LIFTLIB #478] ott の合否判定 (cli.ott_judge) のネガコン。参照成果物の欠落 (None) を合格にしないこと,
    junkHi は --auto none の合否に使わないこと, auto 既定は junkHi 閾値で落ちることを固定する。"""
    from liftlib.cli import ott_judge, OTT_AUTO_JUNKHI_MAX
    ident = {k: True for k in ("O1", "O2a", "O2b", "O2c", "O3a", "O3b", "O4")}
    oh = dict(combos=42, equal=True, distinct=40, f0_equal=21, f0_total=21)
    census = lambda jh: json.dumps({"junkHi": jh})          # noqa: E731
    good = dict(**{"pass": True}, outhash=oh, census0=census(175))
    # 正: 全て揃えば junkHi 175 でも PASS (junkHi は --auto none の合否に使わない)
    ok, why, miss = ott_judge(good, ident, (), None)
    assert ok and not why and not miss, why
    # NC1: 7 段 IR 一致の 1 段が None (参照 .ll 欠落) → 不合格 + 欠落扱い
    ok, why, miss = ott_judge(good, dict(ident, O4=None), (), None)
    assert not ok and miss and any("O4" in w for w in why), why
    # NC2: IR 不一致 (False) → 不合格 (欠落ではない)
    ok, why, miss = ott_judge(good, dict(ident, O2a=False), (), None)
    assert not ok and not miss and any("O2a" in w for w in why), why
    # NC3: outhash 未実施 (参照 ott_m10.cjs 欠落) → 不合格 + 欠落扱い
    ok, why, miss = ott_judge(dict(good, outhash=None), ident, (), None)
    assert not ok and miss, why
    # NC4: outhash 不一致 → 不合格
    bad_oh = dict(oh, equal=False, f0_equal=20)
    ok, why, miss = ott_judge(dict(good, outhash=bad_oh), ident, (), None)
    assert not ok and not miss and any("outhash" in w for w in why), why
    # NC5: outhash 実行失敗 → 不合格
    ok, why, miss = ott_judge(dict(good, outhash=dict(error="x")), ident, (), None)
    assert not ok, why
    # NC6: e2e 不合格 (r[pass]=False) → 不合格
    ok, why, miss = ott_judge(dict(good, **{"pass": False}), ident, (), None)
    assert not ok, why
    # auto 既定: junkHi 閾値ちょうどは PASS / 超過・取得不能は FAIL。IR 一致 None でも auto は影響されない
    auto = ("f2", "f7", "p1")
    a_ok = {"pass": True, "outhash": None, "census0": census(OTT_AUTO_JUNKHI_MAX)}
    assert ott_judge(a_ok, {k: None for k in ident}, auto, None)[0]
    assert not ott_judge(dict(a_ok, census0=census(OTT_AUTO_JUNKHI_MAX + 1)), ident, auto, None)[0]
    assert not ott_judge(dict(a_ok, census0=None), ident, auto, None)[0]
    print("T18 ok (ott_judge: 正 1 / ネガコン NC1 IR None・NC2 IR 不一致・NC3 outhash 未実施・NC4 不一致・NC5 失敗・NC6 e2e 不合格・auto junkHi 閾値)")


def t19():
    """SR-4 (#75): S1c movl/h(ps|pd) の store 復元 + Image.add_func (.pdata 外 leaf の合成エントリ)。"""
    blk = {"function_x": "\n".join([
        "  %a = load i64, ptr %p, align 8, !insn.addr !1",
        "  call void @__asm_movlps(i64 %a, i128 %v), !insn.addr !2",
        "  %b = load i64, ptr %q, align 8, !insn.addr !3",
        "  call void @__asm_movhpd(i64 %b, i128 %w), !insn.addr !4",
        "  %c = add i64 %b, 1",
        "  call void @__asm_movlps(i64 %c, i128 %v), !insn.addr !5"])}
    out, n = base.lower_asm_lane_store(dict(blk))
    t = out["function_x"]
    assert n == 2, n
    assert "store i64 %s1c_0_lo, ptr %p" in t and "%s1c_0_lo = trunc i128 %v to i64" in t, t
    assert "%s1c_1_sh = lshr i128 %w, 64" in t and "store i64 %s1c_1_lo, ptr %q" in t, t
    assert "call void @__asm_movlps(i64 %c, i128 %v)" in t     # load 由来でない旧値は触らない (simd 生成側が unsupported 報告)
    same, n0 = base.lower_asm_lane_store({"f": "  %x = add i64 1, 2"})
    assert n0 == 0 and same == {"f": "  %x = add i64 1, 2"}
    img = Image(os.path.join(T, "targets/serum2/work/Serum2_win64.vst3")) if os.path.exists(os.path.join(T, "targets/serum2/work/Serum2_win64.vst3")) else None
    if img is None:
        print("T19 ok (S1c 合成 IR; add_func は Serum2 PE 無しで skip)")
        return
    assert img.func_at(0x1802f7370) is None
    img.add_func(0x1802f7370, 0x1802f74ec)
    assert img.func_at(0x1802f7380) == (0x1802f7370, 0x1802f74ec)
    try:
        img.add_func(0x1802f7510, 0x1802f7520)     # .pdata 関数 (0x1802f7510-0x1802fcc82) と重なる
        raise SystemExit("T19 FAIL: overlap not rejected")
    except ValueError:
        pass
    print("T19 ok (S1c movlps/movhpd store 復元 2 件 + 非 load 旧値は不変 + Image.add_func 登録/重複拒否)")


def t20():
    """SR-4 (#75): F2 の D5 型 (xmm 引数が `sext i64 %argN` に束ねられた形) 検出。"""
    from liftlib.passes import f2
    ll = "\n".join([
        "define i64 @function_18008b2a0(i64 %arg1) local_unnamed_addr {",
        "dec_label_pc_18008b2a0:",
        "  %2 = sext i64 %arg1 to i128, !insn.addr !0",
        "  %3 = call i64 @__asm_movss__qx(i128 %2), !insn.addr !0",
        "  %4 = sext i64 %arg1 to i128, !insn.addr !1",
        "  %5 = call i64 @__asm_movss__qx(i128 %4), !insn.addr !2",
        "  ret i64 0, !insn.addr !2",
        "}",
        "declare i64 @__asm_movss__qx(i128) local_unnamed_addr",
        "!0 = !{i64 6443020960}", "!1 = !{i64 6443020965}", "!2 = !{i64 6443020970}", ""])
    mod = IR.Module.parse(ll)
    fn = mod.funcs()[0]
    hit = f2.find_sext_arg_for(mod, fn, [6443020960])
    assert hit is not None and hit[2] == "%2", hit                 # reader アドレス上でのみ使われる sext
    assert f2.find_sext_arg_for(mod, fn, [6443020999]) is None     # reader 外 -> 対象外
    assert f2.find_sext_arg_for(mod, fn, [6443020960, 6443020970]) is not None
    print("T20 ok (F2 D5 型: reader 上の sext i64 %arg を xmm 値定義として検出 / reader 外は不検出)")



def t21():
    """[LIFTLIB-5 / #342] leafabi: `_ret_thread` の名前割当 `fresh` はループ前に束縛される。

    ret が全て reg2mem phi 分岐に入る構成 (最初に処理する ret が phi) で UnboundLocalError にならず,
    同一 ret VA の複製 ret にも衝突しない名前が付く。`_rx_one` の phi load 名は block を跨いで衝突しない。
    """
    from types import SimpleNamespace as NS
    from liftlib import mc
    from liftlib.passes import leafabi

    class _Mod:
        def addr_of(self, ln):
            return 0x1000
        def tag(self, va):
            return ""

    class _Ix:
        defs = {}
        def dominators(self):
            return {0: {0}, 1: {0, 1}}

    class _Binder:
        ix = _Ix()
        def bind(self, reg, va):
            return None

    prev, prev_phi = mc.LEAF_EXT, leafabi._call_phi
    mc.LEAF_EXT = True
    leafabi._call_phi = lambda mod, fn, binder, va, used: "%phia"
    try:
        fn = NS(name="function_1000", blocks=[NS(lines=["  %a = add i64 0, 0", "  ret i64 %a"]),
                                              NS(lines=["  ret i64 0"])])
        st = {}
        leafabi._ret_thread(_Mod(), fn, None, _Binder(), [], st)
    finally:
        mc.LEAF_EXT, leafabi._call_phi = prev, prev_phi
    assert st["ret_phi"] == 2 and st.get("ret_unbound", 0) == 0, st
    names = [l.split(" = ")[0].strip() for b in fn.blocks for l in b.lines if " = " in l]
    assert len(names) == len(set(names)), names
    for b in fn.blocks:
        assert b.lines[-1].startswith("  ret i64 %lf_1000_t"), b.lines
        assert any("load i128, ptr %phia" in l for l in b.lines), b.lines
    print("T21 ok (leafabi _ret_thread: phi 分岐が先頭 ret でも fresh 束縛済み, 複製 ret の名前は %d 個すべて一意)" % len(names))


def t22():
    """[LIFTLIB-5 / #342] p1 `_setcc_value`: `xor r,r` のゼロ化は setcc と同一の機械語 block 内, かつ 32bit 以上に限る。

    (A) 同一 block の xor r10d,r10d → 復元する (tan @1801a9cd9 の形)
    (B) xor が別 block (jz で setcc 側へ迂回できる) → 復元しない (別 pred の xor を信用すると上位 56bit が不定)
    (C) xor r10b,r10b (8bit) → 復元しない (上位 bit を消さない)
    GPR spill slot: reload は領域内の全 pred 経路で store 済みの slot に限る (st["__gw"] の交わり)。
    """
    from types import SimpleNamespace as NS
    from liftlib import mc
    from liftlib.passes import p1

    class _Img:
        def __init__(self, code):
            self.code = code
        def read(self, va, n):
            return self.code[va - 0x1000:va - 0x1000 + n]

    cmp_set_ret = bytes.fromhex("39d1" "410f95c2" "c3")                  # cmp ecx,edx ; setne r10b ; ret
    cases = {
        "A_same_block": (bytes.fromhex("4531d2") + cmp_set_ret, True),   # xor r10d,r10d
        "B_other_block": (bytes.fromhex("85c0" "7403" "4531d2") + cmp_set_ret, False),   # test; jz +3; xor r10d,r10d | setcc
        "C_xor8": (bytes.fromhex("4530d2") + cmp_set_ret, False),        # xor r10b,r10b
    }
    prev = mc.LEAF_EXT
    mc.LEAF_EXT = True
    try:
        got = {}
        for name, (code, want) in cases.items():
            mf = MFunc(_Img(code), 0x1000, 0x1000 + len(code))
            d = next(v for v in mf.order if mf.insns[v].mnem.startswith("set"))
            stub = NS(mf=mf, mod=NS(tag=lambda va: ""), b=NS(_is_region_dst=lambda n: False),
                      ix=NS(instrs_at=lambda a: [(0, 0, "  %c = icmp ne i32 %a, %b")]),
                      _value_ok=lambda n, u: True, nm=lambda va, t: "%sz", used=lambda k: None)
            out = []
            v = p1.Region._setcc_value(stub, "r10", d, d, out)
            got[name] = v is not None
            assert (v is not None) == want, (name, v, out)
    finally:
        mc.LEAF_EXT = prev
    print("T22 ok (p1 _setcc_value: " + ", ".join("%s=%s" % (k, "復元" if v else "拒否") for k, v in got.items()) + ")")


def t23():
    """[LIFTLIB-11 / #887] canon_alloca_order: 行順・struct の同先頭トークン (tie)・配列の型名で canon 出力が変わらない。"""
    def fn(rows):
        return "\n".join(["define void @function_1000() {", "entry:"] + ["  %%%s = alloca %s" % (n, t) for n, t in rows]
                         + ["  store i32 0, ptr %3", "  ret void", "}"])
    base_rows = [("3", "i32"), ("4", "i8"), ("5", "{ i32, i8 }, align 4"), ("6", "{ i64, i64 }, align 8"), ("7", "[8 x i8], align 1")]
    ref = base.canon_alloca_order(fn(base_rows))
    for perm in ([4, 3, 2, 1, 0], [2, 0, 4, 1, 3], [1, 0, 2, 3, 4]):
        got = base.canon_alloca_order(fn([base_rows[i] for i in perm]))
        assert got == ref, (perm, got, ref)
    # スロット名は番号の昇順に振り直され、型名順 ([ < i < {) で割り当たる
    lines = [l for l in ref.split("\n") if "alloca" in l]
    assert [l.split(" = ")[0].strip() for l in lines] == ["%3", "%4", "%5", "%6", "%7"], lines
    assert lines[0].endswith("alloca [8 x i8], align 1"), lines
    # struct 同士の tie (先頭 `{`) が入力順に依存しない
    s_a = base.canon_alloca_order(fn([("3", "{ i32, i8 }, align 4"), ("4", "{ i64, i64 }, align 8")]))
    s_b = base.canon_alloca_order(fn([("4", "{ i64, i64 }, align 8"), ("3", "{ i32, i8 }, align 4")]))
    assert s_a == s_b, (s_a, s_b)
    # 同型 alloca 2 本の行順入替え (store は %4 を指す): 参照先が入力順に依存しない
    def fs(rows, store):
        return "\n".join(["define void @function_1000() {", "entry:"] + ["  %%%s = alloca i32, align 4" % n for n in rows]
                         + ["  store i32 0, ptr %%%s" % store, "  ret void", "}"])
    t_a = base.canon_alloca_order(fs(["3", "4"], "4"))
    t_b = base.canon_alloca_order(fs(["4", "3"], "4"))
    assert t_a == t_b, (t_a, t_b)
    assert t_a.endswith("  store i32 0, ptr %4\n  ret void\n}"), t_a
    print("T23 ok (canon_alloca_order: 行順 3 通り・struct tie・配列型名で canon 出力一致, slot は %3..%7 昇順)")


def t24():
    """[#1269] icall.blk_global_text: BLK 範囲内の inttoptr 定数だけ @__icall_blk への GEP に張り替え、宣言を最初の declare/define の前へ入れる。"""
    from liftlib.passes import icall
    blk = 0x184308000
    src = "\n".join(["target datalayout = \"e-p:32:32\"", "declare i64 @function_1000()", "define i64 @function_1001() {", "entry:",
                     "  %%a = load i64, ptr inttoptr i64 %d to ptr" % blk,
                     "  %%b = load i64, ptr inttoptr i64 %d to ptr" % (blk + 8),
                     "  %%c = load i64, ptr inttoptr i64 %d to ptr" % (blk + 0x1FF),
                     "  %%d = load i64, ptr inttoptr i64 %d to ptr" % (blk + 0x200),
                     "  %%e = load i64, ptr inttoptr i64 %d to ptr" % (blk - 1),
                     "  ret i64 %a", "}", ""])
    out, n = icall.blk_global_text(src, blk)
    assert n == 3, n
    for off in (0, 8, 0x1FF):
        assert "getelementptr inbounds i8, ptr @__icall_blk, i64 %d" % off in out, off
    for v in (blk + 0x200, blk - 1):
        assert "inttoptr i64 %d to ptr" % v in out, v
    decl = "@__icall_blk = external global [512 x i8], align 16"
    assert out.count(decl) == 1
    assert out.index(decl) < out.index("declare i64 @function_1000"), out
    far = "\n".join(["define i64 @function_1001() {", "entry:",
                     "  %%a = load i64, ptr inttoptr i64 %d to ptr" % (blk + 0x1000), "  ret i64 %a", "}", ""])
    untouched, n0 = icall.blk_global_text(far, blk)
    assert n0 == 0 and untouched == far, untouched
    print("T24 ok (blk_global_text: 範囲内 3 件を GEP へ, 範囲外 2 件は不変, 宣言は declare 前, 置換 0 件は無変更)")


def t25():
    base, newbase = 0x180000000, 0x30000000
    src = "\n".join(["define i64 @f(i64 %x) {",
                     "  %a = add nuw nsw i64 %x, 6442450944",
                     "  %b = add nsw i64 %a, 6443624176",
                     "  %c = add i64 %x, 1",
                     "  %d = add i64 %x, 6442450943",
                     "  ret i64 %b", "}", ""])
    off, n0 = remap.shift_va(src, base, newbase, maxv=0x1803FFFFF)
    assert "add nuw nsw i64 %x, 6442450944" in off and n0 == 0, off
    on, n1 = remap.shift_va(src, base, newbase, maxv=0x1803FFFFF, add_forms=True)
    assert "add nuw nsw i64 %x, 805306368\n" in on, on
    assert "add nsw i64 %a, 806479600\n" in on, on
    assert "add i64 %x, 1\n" in on and "add i64 %x, 6442450943" in on, on
    assert n1 == 2, n1
    print("T25 ok (add_forms: 加算形の画像 VA を shift, 範囲外・既定 False は不変)")


def t26():
    """T26 (#2863): IR 一致ゲートの `%pc` 改名に対する感度。空行を除いた入力では p1 の一時名 (行 index) が変わるが,
    改名を除けば内容は一致する。(ネガ) 比較述語 1 箇所 (ult→ule) の変更は一致しない。(別算法) 行対応の写像が一意かつ単射。"""
    import tempfile
    from liftlib.recipes import ott as OTT
    M6 = os.path.join(T, "m6/work")
    raw = open(os.path.join(M6, "ott_lift.ll")).read()
    o, st = p1_legacy.legacy_p1("\n".join(nb(raw)) + "\n")   # 空行を除いた入力
    ref = p1_legacy.legacy_p1(raw)[0]                        # 空行入りの入力 (修正後の出力同士で比べる)
    assert o != ref                                   # 前提: 名前は行 index 依存で変わる
    assert nb(p1_legacy.canon_tags(o)) == nb(p1_legacy.canon_tags(ref))
    bad = re.sub(r"fcmp ult (float|double) %pc", r"fcmp ule \1 %pc", ref, count=1)
    assert bad != ref and nb(p1_legacy.canon_tags(bad)) != nb(p1_legacy.canon_tags(ref))
    with tempfile.NamedTemporaryFile("w", suffix=".ll", delete=False) as f:
        f.write(ref)
    try:
        assert OTT.same(o, f.name) is True and OTT.same(bad, f.name) is False
    finally:
        os.remove(f.name)
    # 修正前参照 (work/ のみ・R2 再投入まで据え置き): 改名を除いた差は repmap の 18 行だけ (repmap_delta)。
    # R2 再投入で参照が修正後になったら, この 1 行を `canon(o) == canon(参照)` の完全一致に戻す。
    pre = open(os.path.join(M6, "ir7e_p1.ll")).read()
    assert repmap_delta("\n".join(nb(p1_legacy.canon_tags(o))), "\n".join(nb(p1_legacy.canon_tags(pre)))) == 18
    a, b = nb(o), nb(ref)
    assert len(a) == len(b)
    m = {}
    for x, y in zip(a, b):
        X, Y = re.findall(r"%pc(\d+)[a-z]", x), re.findall(r"%pc(\d+)[a-z]", y)
        assert len(X) == len(Y)
        for p, q in zip(X, Y):
            assert m.setdefault(p, q) == q            # 写像は一意
    assert len(set(m.values())) == len(m)             # 単射
    print("T26 ok (%%pc 改名だけ無視: 行 %d・改名 %d 種・ネガ FAIL 確認・修正前参照との差は repmap 18 行)" % (len(a), len(m)))


def t27():
    """[LIFTLIB-23 #3145] ott_outhash の出力読取 (recipes/ott.outhash_json)。stdout に JSON 以外の行が混じっても最後の JSON 行を読む。
    JSON が無い失敗 (module の exit 等) は rc と stdout/stderr の抜粋を例外に残し, 「Expecting value」だけで終わらせない。"""
    import subprocess
    from liftlib.recipes import ott as OTT
    good = subprocess.CompletedProcess(["node"], 0, stdout='noise\n{"p0_f0_a0": "ab"}\n', stderr="")
    assert OTT.outhash_json(good) == {"p0_f0_a0": "ab"}
    bad = subprocess.CompletedProcess(["node"], 1, stdout="", stderr="[m6_rt] FAIL: fail-fast stub called\n")
    try:
        OTT.outhash_json(bad)
    except RuntimeError as ex:
        assert "rc=1" in str(ex) and "fail-fast" in str(ex), str(ex)
    else:
        raise AssertionError("JSON 無しは例外になること")
    print("T27 ok (ott_outhash 出力読取: 混在行の最後の JSON を読む・JSON 無しは rc と stderr を例外に残す)")


def t27b():
    """[LIFTLIB-23 #3145] 参照 module の .wasm 欠落の再現 (前回 run の outhash 失敗の原因)。node は stdout 空・rc=1 で
    終わり、stderr に ENOENT (`.wasm`) が残る。outhash_json はこの stderr を例外に残すこと。"""
    import shutil
    import subprocess
    import tempfile
    from liftlib.recipes import ott as OTT
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    src = os.path.join(root, "tools", "m10", "work", "ott_m10.cjs")
    if not os.path.exists(src):
        print("T27b skip (tools/m10/work/ott_m10.cjs 無し・素材 work-m6-ott)")
        return
    d = tempfile.mkdtemp()
    try:
        shutil.copy(src, d)
        mjs = os.path.join(root, "tools", "liftlib", "liftlib", "recipes", "ott", "ott_outhash.mjs")
        r = subprocess.run(["node", mjs], capture_output=True, text=True, env=dict(os.environ, OTT_CJS=os.path.join(d, "ott_m10.cjs")), timeout=300)
        try:
            OTT.outhash_json(r)
        except RuntimeError as ex:
            assert "rc=1" in str(ex) and ".wasm" in str(ex), str(ex)
        else:
            raise AssertionError(".wasm 無しは JSON 無しの例外になること")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("T27b ok (.wasm 欠落の module は stdout 空・rc=1・stderr の ENOENT を例外に残す)")


def _entry_fn(params, body):
    text = "\n".join(["define i64 @function_18011e5a0(%s) local_unnamed_addr {" % params, "dec_label_pc_18011e5a0:"]
                     + body + ["}", ""])
    return IR.Module.parse(text).func("function_18011e5a0")


def t28():
    """[#1270 review] entry_blk_args の正常系: 入口の BLK+0x08/+0x10 読みを仮引数 %argN へ張り替える。
    型は i64 = add, ptr = ptrtoint, i1/i8/i16/i32 = zext。読まれる slot に仮引数が無ければ触らない。"""
    from liftlib.passes import icall
    body = ["  %g1 = getelementptr inbounds i8, ptr @__icall_blk, i64 8",
            "  %a = load i64, ptr %g1, align 8, !insn.addr !1",
            "  %g2 = getelementptr inbounds i8, ptr @__icall_blk, i64 16",
            "  %b = load i64, ptr %g2, align 8, !insn.addr !2",
            "  %c = add i64 %a, %b",
            "  ret i64 %c"]
    fn = _entry_fn("ptr %arg1, i64 %arg2", body)
    assert icall.entry_blk_args(fn) == 2
    lines = fn.blocks[0].lines
    assert "  %a = ptrtoint ptr %arg1 to i64, !insn.addr !1" in lines, lines
    assert "  %b = add i64 %arg2, 0, !insn.addr !2" in lines, lines
    fn = _entry_fn("i64 %arg1, i64 %arg2", body)
    assert icall.entry_blk_args(fn) == 2
    assert "  %a = add i64 %arg1, 0, !insn.addr !1" in fn.blocks[0].lines
    for ty in ("i1", "i8", "i16", "i32"):
        fn = _entry_fn("%s %%arg1, i64 %%arg2" % ty, body)
        assert icall.entry_blk_args(fn) == 2, ty
        assert "  %%a = zext %s %%arg1 to i64, !insn.addr !1" % ty in fn.blocks[0].lines, ty
    fn = _entry_fn("ptr %arg1", body)
    assert icall.entry_blk_args(fn) == 1
    assert "  %b = load i64, ptr %g2, align 8, !insn.addr !2" in fn.blocks[0].lines
    print("T28 ok (entry_blk_args 正常系: ptr=ptrtoint / i64=add / i1,i8,i16,i32=zext, 仮引数の無い slot は不変)")


def t29():
    """[#1270 review] entry_blk_args の break 条件: 入口 block で BLK への store・分岐・非 asm の call より後の BLK 読みは置換しない。
    call は tail / musttail / notail 付きも対象。@__asm_ helper の call は break しない。"""
    from liftlib.passes import icall
    head = ["  %g1 = getelementptr inbounds i8, ptr @__icall_blk, i64 8"]
    read = "  %a = load i64, ptr %g1, align 8"
    for call in ("%x = tail call void @f()", "%x = musttail call void @f()", "%x = notail call void @f()", "call void @f()"):
        fn = _entry_fn("i64 %arg1", head + ["  " + call, read, "  ret i64 %a"])
        assert icall.entry_blk_args(fn) == 0 and read in fn.blocks[0].lines, call
    for call in ("call void @__asm_foo()", "%x = tail call void @__asm_foo()"):
        fn = _entry_fn("i64 %arg1", head + ["  " + call, read, "  ret i64 %a"])
        assert icall.entry_blk_args(fn) == 1, call
    fn = _entry_fn("i64 %arg1, i64 %arg2", head + [read, "  %x = tail call void @f()",
                                                 "  %g2 = getelementptr inbounds i8, ptr @__icall_blk, i64 16",
                                                 "  %b = load i64, ptr %g2, align 8", "  ret i64 %b"])
    assert icall.entry_blk_args(fn) == 1
    assert "  %a = add i64 %arg1, 0" in fn.blocks[0].lines and "  %b = load i64, ptr %g2, align 8" in fn.blocks[0].lines
    print("T29 ok (entry_blk_args break: tail/musttail/notail/plain call の後の読みは不変 / asm helper は break しない / call 前の読みは置換)")


def t30():
    """[#1270 review] entry_blk_args: 読まれる slot の仮引数が float/double/vector 等の非対応型なら ValueError にする (誤 IR を出さない)。読まれない slot の型は問わない。"""
    from liftlib.passes import icall
    head = ["  %g1 = getelementptr inbounds i8, ptr @__icall_blk, i64 8", "  %a = load i64, ptr %g1, align 8", "  ret i64 %a"]
    for ty in ("double", "float", "<2 x i64>"):
        fn = _entry_fn("%s %%arg1, i64 %%arg2" % ty, head)
        try:
            icall.entry_blk_args(fn)
        except ValueError as ex:
            assert "unsupported param type %r" % ty in str(ex), str(ex)
        else:
            raise SystemExit("T30: %s が通ってしまった" % ty)
    fn = _entry_fn("i64 %arg1, double %arg2", head)
    assert icall.entry_blk_args(fn) == 1 and "  %a = add i64 %arg1, 0" in fn.blocks[0].lines
    print("T30 ok (entry_blk_args: float/double/<2 x i64> の読まれる slot は ValueError, 読まれない slot の型は不問)")


def t31():
    """[#1270 review] pipeline.image_bytes_c: cfg.image_bytes が無い (空を含む) ときは Image を読まず None を返す。"""
    from liftlib import pipeline
    cfg = {"name": "nosuch", "image": "targets/no_such_image.dll", "passes": {"shift": {"newbase": "0x30000000"}}}
    assert pipeline.image_bytes_c(cfg, HERE) is None
    assert pipeline.image_bytes_c(dict(cfg, image_bytes=[]), HERE) is None
    print("T31 ok (image_bytes_c: image_bytes 無し・空は None (存在しない image は読まない))")


def t32():
    """[LIFTLIB-26 / #4350] p1 `bsr r64,r64`: ZF=(src==0) を整数 flag 状態に載せ、src==0 のとき dst は前値を保つ。

    合成機械語 `48 0f bd c1` (bsr rax,rcx) を lift_data_insn に通し、生成 IR に ctlz と select が出ること、
    flag 状態が ("int", (src, 0)) になることを固定する (cmp rcx,0 の既存経路と同じ ZF の読み方になる)。"""
    from types import SimpleNamespace as NS
    from liftlib.passes import p1
    from liftlib import ir as IR

    mod = IR.Module.parse("define void @function_1000() {\nentry:\n  ret void\n}\n")
    out = []
    st = {"__w": set(), "rax": ("%old", "i64"), "rcx": ("%src", "i64"), "fl": None}
    it = NS(va=0x1000, mnem="bsr", op_str="rax, rcx", mem=None, is_call=False,
            ops=[NS(type=1, reg="rax"), NS(type=1, reg="rcx")],
            _ci=NS(operands=[NS(size=8), NS(size=8)]))
    stub = NS(mod=mod, nm=lambda va, t: "%%%s_%d" % (t, len(out)), used=lambda k: None,
              _GPR_ALU=p1.Region._GPR_ALU, _gpr_val=lambda st_, reg, va, o, bits=64: st_[reg][0])
    res = p1.Region.lift_data_insn(stub, it, [("reg", "rax"), ("reg", "rcx")], st, out, "")
    text = "\n".join(out)
    assert res is True, res
    assert "call i64 @llvm.ctlz.i64(i64 %src, i1 true)" in text, text
    assert "icmp eq i64 %src, 0" in text and "select i1" in text, text
    assert st["fl"] == ("bsrzf", ("%src", 64)), st["fl"]
    assert any(isinstance(l, str) and l.startswith("declare i64 @llvm.ctlz.i64") for l in mod.items), mod.items[:2]
    stub._flag_zf_i1 = lambda *a: p1.Region._flag_zf_i1(stub, *a)
    stub._flag_cc_i1 = lambda *a: p1.Region._flag_cc_i1(stub, *a)
    stub._flag_cf_i1 = lambda *a: p1.Region._flag_cf_i1(stub, *a)
    o2 = []
    c = stub._flag_cc_i1(st, "e", o2, 0x1000, "")
    assert c is not None and "icmp eq i64 %src, 0" in "\n".join(o2), o2
    for bad in ("b", "l", "s", "a"):
        try:
            stub._flag_cc_i1(st, bad, [], 0x1000, "")
        except p1.Unsupported:
            continue
        raise AssertionError("bsr の直後の cc %s は Unsupported のはず" % bad)
    print("T32 ok (bsr r64: ctlz + select(src==0 で dst 保持), ZF は bsrzf(src,64)、e/ne 以外の cc は Unsupported)")


def t33():
    """[LIFTLIB-32 / #6080] `cmp rcx,0` の直後の jl (SF/OF) / je (ZF) / jb (CF) の IR を固定し、x86 の定義どおりの値になることを確認する。

    x86 の cmp a,b: 結果 r = a-b (mod 2^bits)。ZF=(r==0), SF=(r の最上位 bit), CF=(a <u b), OF=符号付き溢れ。
    jl = SF!=OF, je = ZF, jb = CF。生成 IR の icmp 述語を Python で評価し、上の定義と全サンプルで一致することを見る。"""
    import re
    from types import SimpleNamespace as NS
    from liftlib.passes import p1
    from liftlib import ir as IR

    mod = IR.Module.parse("define void @function_1000() {\nentry:\n  ret void\n}\n")
    out = []
    st = {"__w": set(), "rcx": ("%rcx", "i64"), "fl": None}
    stub = NS(mod=mod, nm=lambda va, t: "%%%s_%d" % (t, len(out)), used=lambda k: None,
              _GPR_ALU=p1.Region._GPR_ALU, _gpr_val=lambda st_, reg, va, o, bits=64: st_[reg][0])
    stub._flag_zf_i1 = lambda *a: p1.Region._flag_zf_i1(stub, *a)
    stub._flag_cc_i1 = lambda *a: p1.Region._flag_cc_i1(stub, *a)
    stub._flag_cf_i1 = lambda *a: p1.Region._flag_cf_i1(stub, *a)
    cmp_it = NS(va=0x1000, mnem="cmp", op_str="rcx, 0", mem=None, is_call=False,
                ops=[NS(type=1, reg="rcx"), NS(type=2, imm=0)],
                _ci=NS(operands=[NS(size=8), NS(size=8)]))
    res = p1.Region.lift_data_insn(stub, cmp_it, [("reg", "rcx"), ("imm", 0)], st, out, "")
    assert res is True and st["fl"] == ("int", ("%rcx", "0", False, 64)), st["fl"]

    def jcc_ir(cc):
        o = []
        c = p1.Region._int_jcc_cond(stub, NS(cc=cc), st, o, 0x1001, "")
        return c, "\n".join(o)

    def pred_eval(ir, a, bits=64):
        m = re.search(r"icmp (\w+) i%d %%rcx, (-?\d+)" % bits, ir)
        assert m, ir
        p, b = m.group(1), int(m.group(2))
        mask = (1 << bits) - 1
        sa, sb = a & mask, b & mask
        if p in ("slt", "sge", "sle", "sgt"):
            sg = lambda v: v - (1 << bits) if v >> (bits - 1) else v
            sa, sb = sg(sa), sg(sb)
        return {"slt": sa < sb, "sge": sa >= sb, "sle": sa <= sb, "sgt": sa > sb,
                "ult": sa < sb, "uge": sa >= sb, "ule": sa <= sb, "ugt": sa > sb,
                "eq": sa == sb, "ne": sa != sb}[p]

    def x86_flags(a, bits=64):
        mask = (1 << bits) - 1
        ra, rb = a & mask, 0
        r = (ra - rb) & mask
        sign = 1 << (bits - 1)
        sa = ra - (1 << bits) if ra & sign else ra
        sr = r - (1 << bits) if r & sign else r
        zf = r == 0
        sf = bool(r & sign)
        cf = ra < rb
        of = (sa - 0) != sr
        return {"zf": zf, "sf": sf, "cf": cf, "of": of}

    samples = [0, 1, -1, 2, -2, 5, -5, (1 << 63) - 1, 1 << 63, (1 << 63) + 1, (1 << 64) - 2, 0x7FFFFFFF, 0x80000000]
    c_l, ir_l = jcc_ir("l")
    assert "icmp slt i64 %rcx, 0" in ir_l, ir_l
    c_e, ir_e = jcc_ir("e")
    assert "icmp eq i64 %rcx, 0" in ir_e, ir_e
    c_b, ir_b = jcc_ir("b")
    assert "icmp ult i64 %rcx, 0" in ir_b, ir_b
    for a in samples:
        f = x86_flags(a)
        assert pred_eval(ir_l, a) == (f["sf"] != f["of"]), ("jl", a)
        assert pred_eval(ir_e, a) == f["zf"], ("je", a)
        assert pred_eval(ir_b, a) == f["cf"], ("jb", a)
    print("T33 ok (cmp rcx,0: jl=icmp slt(SF!=OF), je=icmp eq(ZF), CF は常に 0 (x86 の定義と %d 値で一致))" % len(samples))


if __name__ == "__main__":
    import traceback
    tests = (t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12, t13, t14, t15, t16, t16b, t16c, t17, t18, t19, t20, t21, t22, t23, t24, t25, t26, t27, t27b, t28, t29, t30, t31, t32, t33)
    fails = []
    for f in tests:
        try:
            f()
        except (Exception, SystemExit):
            fails.append(f.__name__)
            print("%s FAIL" % f.__name__.upper())
            traceback.print_exc()
    if fails:
        print("FAIL %d/%d: %s" % (len(fails), len(tests), " ".join(fails)))
        sys.exit(1)
    print("ALL UNIT TESTS PASS (%d)" % len(tests))
