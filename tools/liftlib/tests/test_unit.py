#!/usr/bin/env python3
"""tests/test_unit.py — liftlib の軽量ユニット/性質テスト (python3 tests/test_unit.py; 約 20 秒)。

  T1 base 正規化が元チェーン (m2+m5) の出力と一致 (FA/KH/OTT の raw .ll)
  T2 p1_legacy / shift / gdata_legacy が OTT 元チェーンの中間成果物と一致
  T3 SIMD 生成が RetDec の接尾番号 (`__N`) に依存しない (接尾を付け替えても生成 C が同一)
  T4 同じ名前でも署名が違えば別 helper になる (FA の mulss(i128,i32) と OTT の mulss(i128,i128))
  T5 mnemonic 被覆: KH census 205 種のうち未被覆は pcmpistri / vinsertf128 のみ
  T6 機械語解析: FA gain の live-in / 到達定義
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
OTT_DLL = "/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll"
DUP = ("declare i64 @function_1803ded20", "declare i64 @function_18004cf20")


def nb(t):
    return [l for l in t.split("\n") if l.strip()]


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
    M6 = os.path.join(T, "m6/work")
    o, st = p1_legacy.legacy_p1(open(os.path.join(M6, "ott_lift.ll")).read())
    assert o == open(os.path.join(M6, "ir7e_p1.ll")).read()
    o2, n = remap.shift_va(o)
    assert o2 == open(os.path.join(M6, "ir7e_p2.ll")).read()
    o3, gst = remap.gdata_legacy(o2, Image(OTT_DLL))
    assert o3 == open(os.path.join(M6, "ir7e_p3.ll")).read()
    print("T2 ok (p1_legacy/shift/gdata == m6 chain; p1 inserts=%d shift=%d gdata=%d)" % (st["inserted"], n, gst["replaced"]))


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
    fa = gen.scan_decls(open(os.path.join(T, "targets/freshair/work/lift_gain/gain_lift.ll")).read())
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
    assert unc == ["pcmpistri", "vinsertf128"], unc
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
        if lo <= r < lo + len(sd) - 8:
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


if __name__ == "__main__":
    for f in (t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12, t13, t14, t15):
        f()
    print("ALL UNIT TESTS PASS")
