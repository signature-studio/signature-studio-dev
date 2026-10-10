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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
T = os.path.join(HERE, "..", "..")

from liftlib import ir as IR                       # noqa: E402
from liftlib.passes import base, p1_legacy, remap  # noqa: E402
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


if __name__ == "__main__":
    for f in (t1, t2, t3, t4, t5, t6):
        f()
    print("ALL UNIT TESTS PASS")
