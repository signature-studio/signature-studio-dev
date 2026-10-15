"""cli.py — python3 -m liftlib <command>

  build <cfg.json> [--profile std]      標準ビルド入口 (PERF-P1 / #155): RetDec → 修復 → helper → 標準設定 (-O3 -flto + gc-sections + 最小 export)
                                        + 署名ガード (ref/o2/o3/std の全変種で出力署名が一致しなければ exit 1・<name>.cjs を作らない)
  lift <cfg.json> [--n N] [--no-diff]   RetDec → 修復 pass → helper 自動生成 → emcc (旧 -O1) → 差分ハーネス (実機 vs wasm)
  detect <cfg.json>                     修復せず検出器だけ実行 (P1/F7/F2 の所見を JSON で出力)
  diagnose <cfg.json>                   pass 単位の対照実験 (どの修復が必須か) + 未修復所見
  simd gen <ll...> -o out.c [--canon]   __asm_* 宣言から C helper 生成
  simd test                             生成 helper を実機 inline asm と bit 突合 (KH census 205 mnemonic の全 form)
  simd report                           KH mnemonic census の被覆 before/after
  ott [--auto f2|f7|p1|f2,f7,p1|none]   OTT を liftlib 側だけで再現 (m10_e2e 相当)。--auto 既定 = f2,f7,p1 (CAB-238・LIFTLIB-3)。
  inject-eval                           パターン注入による検出器の検出力/偽陽性評価
  specgen <image> <func_va>             機械語から harness spec の雛形を生成 (ポインタ/フィールド推定)
  regress                               OTT / FA Gain / KH Gain の回帰 (liftlib_e2e.sh から呼ぶ)
  boolret <in.ll> <out.ll>              call i1 @F の結果の sext i1→i64 を zext にする (LD-147 / #3180・件数を出力)
"""
import argparse
import json
import os
import sys
import time

from . import pipeline, env
from . import stdbuild as SB
from .harness import diff as D

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, ".."))


def _spec_for(cfg):
    return json.load(open(os.path.join(PKG, cfg["spec"])))


def cmd_lift(a):
    cfg, wd, cjs, stats, log = pipeline.run_all(a.cfg, workdir=a.workdir)
    print("[lift] %s: base=%s" % (cfg["name"], json.dumps(stats.get("base"))))
    for k in ("p1", "f7", "f2", "gdata", "simd", "stubs"):
        if k in stats:
            print("[lift]   %s: %s" % (k, json.dumps(stats[k], ensure_ascii=False)))
    for l in log:
        if "reconstructed" in l or "repaired" in l or l.startswith("f2: F2 call"):
            print("[lift]   " + l)
    if a.no_diff:
        return 0
    spec = _spec_for(cfg)
    s = D.run_diff(pipeline.rpath(cfg["image"]), int(cfg["func_va"], 16), spec, cjs, os.path.join(wd, cfg["name"] + "_fixed.ll"),
                   cfg["wasm_func"], os.path.join(wd, "diff"), n=a.n, timeout=a.timeout)
    print("[diff] %s: %s" % (cfg["name"], D.fmt(s)))
    for d in s["details"][:3]:
        print("[diff]   mismatch", d)
    ok = s["mismatch"] == 0 and s["native_crash"] == 0 and s["match"] > 0
    print("[lift] RESULT %s: %s" % (cfg["name"], "BIT-EXACT %d/%d steps (%d scenarios)" % (s["match"], s["steps"], s["scenarios"]) if ok else "FAIL"))
    return 0 if ok else 1


def cmd_build(a):
    variants = [v for v in a.variants.split(",") if v] if a.variants else None
    try:
        cfg, wd, cjs, stats, log, rep = pipeline.run_build(a.cfg, workdir=a.workdir, profile=a.profile, variants=variants, n=a.n,
                                                           expect=a.expect, timeout=a.timeout)
    except SB.SignatureMismatch as e:
        print("[build] FAIL (署名ガード): %s" % e, file=sys.stderr)
        return 1
    for v, r in rep["variants"].items():
        print("[build]   %-5s wasm %8d B  build %5.1fs  sig %s" % (v, r["wasm_bytes"], r["build_s"], r["sig"]))
    print("[build] PASS %s: profile=%s 署名 %s (%d 変種一致) → %s" % (cfg["name"], a.profile, rep["guard"]["unique"][0], len(rep["variants"]), cjs))
    return 0


def cmd_detect(a):
    cfg, wd, cjs, stats, log = pipeline.run_all(a.cfg, workdir=a.workdir, detect_only=True)
    print(json.dumps(dict(stats=stats, log=log), indent=1, ensure_ascii=False, default=str))
    return 0


def cmd_diagnose(a):
    from . import diag
    r = diag.diagnose(a.cfg, n=a.n)
    print(json.dumps(r, indent=1, ensure_ascii=False, default=str))
    return 0


def cmd_simd(a):
    from .simd import gen, simdtest
    if a.sub == "gen":
        return gen.main(a.rest)
    if a.sub == "test":
        d = json.load(open(os.path.join(PKG, "data/kh_mnemonics.json")))
        bases = sorted(set(d["effects"]) | set(d["infra"]) | set(d["hosts"]))
        forms, stat = simdtest.run(bases=bases, n=a.n, out_dir=os.path.join(PKG, "work/simdtest"), ybases=simdtest.YMM_BASES)
        by = simdtest.summarize(stat)
        bad = [(k, v) for k, v in by.items() if v["mismatch"]]
        tested = sorted(set(k[0] for k in by))
        tot = dict(exact=sum(v["exact"] for v in by.values()), nan_only=sum(v["nan_only"] for v in by.values()),
                   approx_ok=sum(v["approx_ok"] for v in by.values()), mismatch=sum(v["mismatch"] for v in by.values()))
        print("[simd-test] mnemonics=%d tested(native asm)=%d forms=%d vectors=%d %s bad_forms=%d" % (
            len(bases), len(tested), len(by), sum(tot.values()), tot, len(bad)))
        for (b, r, ar), v in bad:
            print("[simd-test] BAD %s %s(%s) %s" % (b, r, ar, v["ex"]))
        return 0 if not bad else 1
    if a.sub == "report":
        return simd_report()
    return 2


def simd_report():
    from .simd import gen
    d = json.load(open(os.path.join(PKG, "data/kh_mnemonics.json")))
    have = set(d["m6_helper_names"])
    allm = set(d["effects"]) | set(d["infra"])
    sets = [("snap-in 固有 closure (効果 42 本)", set(d["effects"])), ("共通基盤 188 関数", set(d["infra"])),
            ("host (Multipass/Snap Heap/Phase Plant)", set(d["hosts"])), ("効果 + 共通基盤", allm),
            ("効果 + 共通基盤 + host", allm | set(d["hosts"]))]
    out = []
    for nm, s in sets:
        cov, unc = gen.coverage(sorted(s))
        out.append(dict(name=nm, mnemonics=len(s), before_uncovered=len(s - have), after_uncovered=len(unc), after_list=unc))
    for r in out:
        print("[simd-report] %-40s mnemonic=%3d  未被覆 before=%3d (m6 helper)  after=%d %s" % (
            r["name"], r["mnemonics"], r["before_uncovered"], r["after_uncovered"], r["after_list"]))
    os.makedirs(os.path.join(PKG, "work"), exist_ok=True)
    json.dump(out, open(os.path.join(PKG, "work/simd_report.json"), "w"), indent=1, ensure_ascii=False)
    return 0


# CAB-238: ott の既定 auto pass 群。旧既定 (m10 chain 再現, 修復無し) は --auto none で切替可。
# LIFTLIB-3: f2 (callee 相) を既定に加えた。CRT leaf の入口 xmm を %xmmK_bits 引数化
# してから f7/p1 を流すと, p1 の dropped 領域で `bind xmm0/xmm1` が成功するようになり
# 残留 21 → 15 / bind xmm0 6 → 1 に減る (census・checks・SHA は不変)。
OTT_AUTO_DEFAULT = "f2,f7,p1"
# CAB-238 検収②: auto f7,p1 で census[0x248]=0 junkHi を 175 → 104 に改善 (既定 f2,f7,p1 でも 104)。悪化 (超過) は FAIL。
OTT_AUTO_JUNKHI_MAX = 104


def parse_auto(s):
    """--auto の値を pass 群 tuple へ。none/off/legacy/空 = 旧既定 (auto 無し)。"""
    s = (s or "").strip().lower()
    if s in ("", "none", "off", "legacy"):
        return ()
    return tuple(x for x in s.split(",") if x)


def _junk_hi(r):
    try:
        return json.loads(r["census0"]).get("junkHi")
    except Exception:                          # noqa
        return None


def ott_judge(r, ident, auto, lb_base):
    """ott の合否判定 (純関数)。戻り値 (ok, 不合格理由 list, 参照欠落 bool)。

    旧既定 (--auto none = m10 chain 再現) の合格条件は 3 つ全て必須で, どれも「判定不能 = 合格」にしない:
      (1) e2e (checks/broken/band maxdev/nbad/trap) = r["pass"]
      (2) 7 段 IR 一致 (O1..O4)。参照 .ll が無く None の段は「欠落」として不合格 (lowbase 時は適用外)
      (3) 出力 SHA 突合 (outhash)。参照 ott_m10.cjs が無い / 実行失敗は「欠落」として不合格
    auto 既定モードは census junkHi <= OTT_AUTO_JUNKHI_MAX。junkHi が取れない (None) 場合も不合格。
    census junkHi 自体は --auto none の合否に使わない (表示値)。
    """
    reasons, missing = [], False
    if not r.get("pass"):
        reasons.append("e2e 不合格 (checks/broken/maxdev/nbad/trap/SHA のいずれか: r[pass]=False)")
    if auto:
        jh = _junk_hi(r)
        if jh is None:
            reasons.append("census junkHi が取得できない")
        elif jh > OTT_AUTO_JUNKHI_MAX:
            reasons.append("census junkHi %d > %d" % (jh, OTT_AUTO_JUNKHI_MAX))
        return (not reasons), reasons, missing
    if lb_base in (None, 0x30000000):
        for k, v in sorted(ident.items()):
            if v is None:
                missing = True
                reasons.append("IR 一致 %s: 参照 .ll が無い (tools/m6/work または tools/m10/work, work-m6-ott 素材)" % k)
            elif v is not True:
                reasons.append("IR 一致 %s: 不一致" % k)
    oh = r.get("outhash")
    if not oh:
        missing = True
        reasons.append("outhash 未実施: 参照 tools/m10/work/ott_m10.cjs が無い")
    elif "error" in oh:
        reasons.append("outhash 実行失敗: %s" % oh["error"])
    elif oh.get("equal") is not True and oh.get("f0_equal") != oh.get("f0_total"):
        reasons.append("outhash 不一致: equal=%s f0 %s/%s" % (oh.get("equal"), oh.get("f0_equal"), oh.get("f0_total")))
    return (not reasons), reasons, missing


def cmd_ott(a):
    from .recipes import ott
    auto = parse_auto(a.auto)
    lb_base = int(a.lb_base, 0) if a.lb_base else None
    W = os.path.join(PKG, "work", "ott" if not auto else "ott_auto_" + "_".join(auto))
    if lb_base not in (None, 0x30000000):
        W += "_lb%x" % lb_base                  # lowbase (CAB-220): base 別に workdir を分ける
    res, log = ott.run(W, build=True, helpers="gen", auto=auto, lb_base=lb_base)
    ident = {k: v for k, v in res.items() if k.startswith("O") and k[1].isdigit() and isinstance(v, (bool, type(None)))}
    print("[ott] layout:", json.dumps(res.get("lb")), "runtime_lb:", json.dumps(res.get("runtime_lb")))
    print("[ott] IR 一致 (liftlib 出力 vs 元チェーン中間成果物):", json.dumps(ident),
          "" if not auto else "(auto 既定モード: 元チェーン一致ゲートは適用外 — m10 再現は --auto none)")
    print("[ott] link:", json.dumps(res.get("link_warnings")), "simd:", json.dumps({k: (v if k != "approx" else len(v)) for k, v in res["simd"].items()}))
    if a.no_e2e:
        return 0
    r = ott.e2e_checks(res["cjs"], W, env_extra=res.get("e2e_env"), outhash=not auto)
    print("[ott] e2e: checks %s / broken %s | band 係数 maxdev=%s nbad=%s | trap rc=%s" % (r["checks"], r["broken"], r["maxdev"], r["nbad"], r["trap_rc"]))
    print("[ott] census[0x248]=0:", r["census0"])
    print("[ott] census[0x248]=1:", r["census1"])
    if r.get("outhash"):
        # outhash は旧既定 (--auto none = m10 chain 再現) モードで実施する (CAB-238: auto 既定モードは
        # 修復由来の SHA 変化が正のため突合を省略し, 差分は REPORT_APPENDIX_A.md §12 の表を参照)。
        print("[ott] 出力 SHA (param×[0x248]×振幅): liftlib 生成 helper 版 vs 元 m10 成果物 =", json.dumps(r["outhash"]))
    ok, reasons, missing = ott_judge(r, ident, auto, lb_base)
    if auto and r.get("census0"):
        print("[ott] census gate (auto 既定): junkHi %s <= %d" % (_junk_hi(r), OTT_AUTO_JUNKHI_MAX))
    for x in reasons:
        print("[ott] NG:", x)
    print("[ott] RESULT:", "PASS" if ok else "FAIL")
    if ok:
        return 0
    return 2 if missing else 1                  # 2 = 参照成果物の欠落 (不一致の 1 と区別する)


def cmd_inject(a):
    from . import inject, ir as IR
    from .pe import Image
    from .passes import base
    T = os.path.join(pipeline.ROOT, "tools")
    out = {}
    for nm in ("fa_gain", "kh_gain"):
        cfg = pipeline.load_cfg(os.path.join(PKG, "targets", nm + ".json"))
        ll = os.path.join(PKG, "work", nm, nm + "_fixed.ll")
        if not os.path.exists(ll):
            continue
        mod = IR.Module.load(ll)
        img = Image(pipeline.rpath(cfg["image"]))
        out[nm] = dict(F7=inject.eval_f7(mod, img), P1_fold=inject.eval_p1_fold(mod, img), F2=inject.eval_f2(mod, img),
                       clean=inject.eval_clean(mod, img))
    m6raw = os.path.join(T, "m6/work/ott.drc.ll")
    if os.path.exists(m6raw):
        text, _ = base.run_base(open(m6raw).read(), base.make_args())
        mod = IR.Module.parse(text)
        img = Image(env.OTT_DLL)
        out["ott"] = dict(F7=inject.eval_f7(mod, img, limit=3, max_total=150), P1_fold=inject.eval_p1_fold(mod, img))
    xl, xd = os.environ.get("LL_XRET_LL"), os.environ.get("LL_XRET_DLL")
    if xl and xd and os.path.exists(xl) and os.path.exists(xd):         # F2 xmm 戻り注入 (LIFTLIB #241)
        from .passes import f2 as F2
        text, _ = base.run_base(open(xl).read(), base.make_args())
        mod = IR.Module.parse(text)
        img = Image(xd)
        F2.run_xmm_ret(mod, img, [], {}, repair=True)
        out["xret"] = dict(F2=inject.eval_f2_xret(mod, img))
    for k, v in out.items():
        print("[inject] %s: %s" % (k, json.dumps(v, ensure_ascii=False)))
    os.makedirs(os.path.join(PKG, "work"), exist_ok=True)
    json.dump(out, open(os.path.join(PKG, "work/inject_eval.json"), "w"), indent=1, ensure_ascii=False)
    inj = sum(x["injected"] for t in out.values() for kk, x in t.items() if kk in ("F7", "P1_fold", "F2"))
    det = sum(x["detected"] for t in out.values() for kk, x in t.items() if kk in ("F7", "P1_fold", "F2"))
    fp = sum(t["clean"]["f7_false_positive"] + t["clean"]["p1_dropped_after_repair"] for t in out.values() if "clean" in t)
    print("[inject] RESULT injected=%d detected=%d false_positive_on_clean=%d" % (inj, det, fp))
    return 0 if inj == det and fp == 0 else 1


def cmd_regress(a):
    rc = 0
    summary = {}
    t0 = time.time()
    for nm in ("fa_gain", "kh_gain"):
        cfgp = os.path.join(PKG, "targets", nm + ".json")

        class A:  # noqa
            cfg, workdir, n, no_diff, timeout = cfgp, None, None, False, 300
        r = cmd_lift(A)
        summary[nm] = "PASS" if r == 0 else "FAIL"
        rc |= r

    class B:  # noqa
        auto, no_e2e, lb_base = OTT_AUTO_DEFAULT, False, None
    r = cmd_ott(B)
    summary["ott"] = "PASS" if r == 0 else "FAIL"
    rc |= r

    class B2:  # noqa
        auto, no_e2e, lb_base = "none", False, None
    r = cmd_ott(B2)                             # 旧既定 (--auto none = m10 chain 再現) の回帰も維持する (CAB-238)
    summary["ott_auto_none"] = "PASS" if r == 0 else "FAIL"
    rc |= r
    summary["elapsed_s"] = round(time.time() - t0, 1)
    print("[regress] " + json.dumps(summary))
    os.makedirs(os.path.join(PKG, "work"), exist_ok=True)
    json.dump(summary, open(os.path.join(PKG, "work/regress.json"), "w"))
    return rc


def cmd_leafspec(a):
    """OTT leaf native spec: leaf closure を base→f2→P1→leafabi→emcc で构建し,
    実機機械語 (native_runner の VA 敷設 + MS x64 ABI 直接実行) と乱数 scenario で bit 突合する。"""
    from .harness import diff as D
    cfg = pipeline.load_cfg(os.path.join(PKG, a.cfg))
    cfg, wd, cjs, stats, log = pipeline.run_all(os.path.join(PKG, a.cfg), workdir=a.workdir)
    print("[leafspec] build %s: %s" % (cfg["name"], json.dumps({k: stats.get(k) for k in ("p1", "f2", "leafabi")}, ensure_ascii=False)))
    for l in log:
        if "leafabi" in l or "reconstructed" in l:
            print("[leafspec]   " + l)
    rc = 0
    summary = {}
    for sp in cfg.get("leaf_specs", []):
        spec = json.load(open(os.path.join(PKG, sp)))
        va = int(spec["func"], 16)
        s = D.run_diff(pipeline.rpath(cfg["image"]), va, spec, cjs, os.path.join(wd, cfg["name"] + "_fixed.ll"),
                       spec["wasm_func"], os.path.join(wd, "diff_" + spec["name"]), n=a.n, timeout=a.timeout)
        summary[spec["name"]] = dict(match=s["match"], mismatch=s["mismatch"], native_crash=s["native_crash"],
                                     wasm_trap=s["wasm_trap"], scenarios=s["scenarios"])
        print("[leafspec] %s: %s" % (spec["name"], D.fmt(s)))
        for d in s["details"][:3]:
            print("[leafspec]   mismatch", d)
        thr = spec.get("expect_match_min")
        if thr is not None:
            # 合格基準 (spec に expect_match_min が在る物のみ gate): crash を除く scenario の一致率
            den = s["scenarios"] - s["native_crash"]
            rate = (s["match"] / den) if den else 0.0
            ok = rate >= thr and s["wasm_trap"] == 0 and s["match"] > 0
            summary[spec["name"]]["expect_match_min"] = thr
            summary[spec["name"]]["match_rate_excl_crash"] = round(rate, 3)
            print("[leafspec]   gate %s: rate=%.3f thr=%.2f -> %s" % (spec["name"], rate, thr, "PASS" if ok else "FAIL"))
            rc |= (0 if ok else 1)
    os.makedirs(os.path.join(PKG, "work"), exist_ok=True)
    json.dump(summary, open(os.path.join(wd, "leafspec_summary.json"), "w"), indent=1)
    print("[leafspec] RESULT:", "PASS" if rc == 0 else "FAIL", json.dumps(summary))
    return rc


def cmd_specgen(a):
    from .harness import specgen
    return specgen.main([a.image, a.va] + (["--name", a.name] if a.name else []))


def cmd_boolret(a):
    from .passes import boolret
    with open(a.src, encoding="utf-8") as f:
        new, n = boolret.apply(f.read())
    with open(a.dst, "w", encoding="utf-8") as f:
        f.write(new)
    print(n)
    return 0


def main(argv=None):
    env.ensure()
    ap = argparse.ArgumentParser(prog="liftlib")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("lift")
    p.add_argument("cfg"); p.add_argument("--n", type=int); p.add_argument("--no-diff", action="store_true")
    p.add_argument("--workdir"); p.add_argument("--timeout", type=int, default=300); p.set_defaults(fn=cmd_lift)
    p = sp.add_parser("build")
    p.add_argument("cfg"); p.add_argument("--profile", default=SB.load()["default_profile"], choices=SB.profile_names())
    p.add_argument("--variants", default="", help="署名ガードの変種 (カンマ区切り; 既定 %s)" % ",".join(SB.load()["guard_variants"]))
    p.add_argument("--expect", help="期待署名 (cfg.signature.expect でも可)"); p.add_argument("--n", type=int, help="署名用シナリオ数 (cfg.signature.n / spec.scenarios)")
    p.add_argument("--workdir"); p.add_argument("--timeout", type=int, default=300); p.set_defaults(fn=cmd_build)
    p = sp.add_parser("detect")
    p.add_argument("cfg"); p.add_argument("--workdir"); p.set_defaults(fn=cmd_detect)
    p = sp.add_parser("diagnose")
    p.add_argument("cfg"); p.add_argument("--n", type=int); p.set_defaults(fn=cmd_diagnose)
    p = sp.add_parser("simd")
    p.add_argument("sub", choices=["gen", "test", "report"]); p.add_argument("rest", nargs="*")
    p.add_argument("--n", type=int, default=200); p.set_defaults(fn=cmd_simd)
    p = sp.add_parser("ott")
    p.add_argument("--auto", default=OTT_AUTO_DEFAULT,
                   help="auto 修復 pass 群 (既定 %s / CAB-238)。none = 旧既定 (m10 chain 再現, 修復無し)" % OTT_AUTO_DEFAULT)
    p.add_argument("--no-e2e", action="store_true")
    p.add_argument("--lb-base", default="", help="V-shift 先 newbase (=LB_BASE)。未指定/0x30000000 は元 m10 chain と同一レイアウト (CAB-220)")
    p.set_defaults(fn=cmd_ott)
    p = sp.add_parser("inject-eval")
    p.set_defaults(fn=cmd_inject)
    p = sp.add_parser("specgen")
    p.add_argument("image"); p.add_argument("va"); p.add_argument("--name", default=""); p.set_defaults(fn=cmd_specgen)
    p = sp.add_parser("leafspec")
    p.add_argument("cfg"); p.add_argument("--n", type=int); p.add_argument("--workdir"); p.add_argument("--timeout", type=int, default=300)
    p.set_defaults(fn=cmd_leafspec)
    p = sp.add_parser("boolret")
    p.add_argument("src"); p.add_argument("dst"); p.set_defaults(fn=cmd_boolret)
    p = sp.add_parser("regress")
    p.set_defaults(fn=cmd_regress)
    a, rest = ap.parse_known_args(argv)
    if a.cmd == "simd" and a.sub == "gen":
        a.rest = a.rest + rest
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
