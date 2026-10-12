"""cli.py — python3 -m liftlib <command>

  lift <cfg.json> [--n N] [--no-diff]   RetDec → 修復 pass → helper 自動生成 → emcc → 差分ハーネス (実機 vs wasm)
  detect <cfg.json>                     修復せず検出器だけ実行 (P1/F7/F2 の所見を JSON で出力)
  diagnose <cfg.json>                   pass 単位の対照実験 (どの修復が必須か) + 未修復所見
  simd gen <ll...> -o out.c [--canon]   __asm_* 宣言から C helper 生成
  simd test                             生成 helper を実機 inline asm と bit 突合 (KH census 205 mnemonic の全 form)
  simd report                           KH mnemonic census の被覆 before/after
  ott [--auto f7|p1|f7,p1|none]         OTT を liftlib 側だけで再現 (m10_e2e 相当)。--auto 既定 = f7,p1 (CAB-238)。
  inject-eval                           パターン注入による検出器の検出力/偽陽性評価
  specgen <image> <func_va>             機械語から harness spec の雛形を生成 (ポインタ/フィールド推定)
  regress                               OTT / FA Gain / KH Gain の回帰 (liftlib_e2e.sh から呼ぶ)
"""
import argparse
import json
import os
import sys
import time

from . import pipeline, env
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
# CAB-238 検収②: auto f7,p1 の census[0x248]=0 junkHi 実測値 (m10 参照 175 から改善)。悪化 (超過) は FAIL。
OTT_AUTO_JUNKHI_MAX = 104


def parse_auto(s):
    """--auto の値を pass 群 tuple へ。none/off/legacy/空 = 旧既定 (auto 無し)。"""
    s = (s or "").strip().lower()
    if s in ("", "none", "off", "legacy"):
        return ()
    return tuple(x for x in s.split(",") if x)


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
        # 修復由来の SHA 変化が正のため突合を省略し, 差分は REPORT.md §12 の表を参照)。
        print("[ott] 出力 SHA (param×[0x248]×振幅): liftlib 生成 helper 版 vs 元 m10 成果物 =", json.dumps(r["outhash"]))
        if not auto:
            if r["outhash"].get("equal") is False and r["outhash"].get("f0_equal") != r["outhash"].get("f0_total"):
                r["pass"] = False
    if auto and r.get("census0"):
        # CAB-238 検収②: auto 既定モードは census 改善 (junkHi ≤ 実測値) の維持を合格条件に含める
        try:
            jh = json.loads(r["census0"]).get("junkHi")
        except Exception:                      # noqa
            jh = None
        if jh is not None:
            ok_jh = jh <= OTT_AUTO_JUNKHI_MAX
            print("[ott] census gate (auto 既定): junkHi %d <= %d -> %s" % (jh, OTT_AUTO_JUNKHI_MAX, "OK" if ok_jh else "NG"))
            r["pass"] = r["pass"] and ok_jh
    ok = r["pass"] and (all(v is True for v in ident.values())
                        if (not auto and lb_base in (None, 0x30000000)) else True)
    print("[ott] RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


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
        img = Image("/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll")
        out["ott"] = dict(F7=inject.eval_f7(mod, img, limit=3, max_total=150), P1_fold=inject.eval_p1_fold(mod, img))
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


def main(argv=None):
    env.ensure()
    ap = argparse.ArgumentParser(prog="liftlib")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("lift")
    p.add_argument("cfg"); p.add_argument("--n", type=int); p.add_argument("--no-diff", action="store_true")
    p.add_argument("--workdir"); p.add_argument("--timeout", type=int, default=300); p.set_defaults(fn=cmd_lift)
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
    p = sp.add_parser("regress")
    p.set_defaults(fn=cmd_regress)
    a, rest = ap.parse_known_args(argv)
    if a.cmd == "simd" and a.sub == "gen":
        a.rest = a.rest + rest
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
