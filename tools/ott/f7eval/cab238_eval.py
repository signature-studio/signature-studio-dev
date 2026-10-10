#!/usr/bin/env python3
"""cab238_eval.py — CAB-238 site 別評価 driver (ott --auto f7,p1 既定化の検証用)。

1 tag = 1 process で実行すること (P1/F7 pass は process 内に monkey-patch するため)。
site / group 単位で修復を絞った OTT build を作り, e2e (checks/census/trap) と
bit-exact 参照 (tools/ott の x64c lifter wasm) との出力 bit 一致数を測る。

  python3 tools/ott/f7eval/cab238_eval.py <tag>   # 単体 (run_eval.sh が並列起動する)

tag は下記 VARIANTS のキー。結果は tools/ott/work/cab238/<tag>/result.json に書く
(recipe が同じ dir に auto_repair.log (site 明細) も出力する)。
  - f7_only    : F7 のみ (P1 無し) — F7 単独の census 寄与
  - f7_ex_<va> : F7 を <va> 以外の 6 site で適用 (production から 1 site 分差し引く)
  - p1_<grp>   : F7 全件 (production と同じ順) + P1 dropped/folded 再構成を <grp> に限定
                 (miswired rewire は常に全件 — production 同様)
絞り込みは liftlib.passes.f7.scan / liftlib.passes.p1.analyze の monkey-patch で行う
(liftlib 本体は無改変)。

検証環境: liftlib = a137396 (CAB-239) + CAB-238 既定化。LIFTLIB_PKG で別 checkout を
指定できる (既定は ../liftlib)。bit 一致の参照は tools/ott/work/lift/ottl.cjs (x64c
lifter, native 実機械語と 89 scenario 50,236 cell bit-exact) を使う。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # tools/ott/f7eval
OTT = os.path.dirname(HERE)                                  # tools/ott
TOOLS = os.path.dirname(OTT)                                 # tools
PKG = os.environ.get("LIFTLIB_PKG") or os.path.join(TOOLS, "liftlib")
OUT = os.path.join(OTT, "work", "cab238")
sys.path.insert(0, PKG)

F7_SITES = [0x18011EF10, 0x18011F00E, 0x18011F9AA, 0x180120632, 0x180120E6A, 0x1801ADDA1, 0x1801C6B5B]
P1_ENV = [0x18011ED6F, 0x18011EDA5, 0x18011EDDC, 0x18011EE12, 0x18011EE49, 0x18011EEB9, 0x18011EF39, 0x18011EF6F]
P1_TAIL = [0x18011FFDD, 0x180120049, 0x18012024B, 0x1801202B7, 0x1801204B9, 0x180120525]

# tag -> (auto, f7_exclude, p1_allow)   exclude/allow = None は絞り無し
VARIANTS = {
    "production": (("f7", "p1"), None, None),   # 既定 (= CAB-238 の gate そのもの) の再測定用
    "f7_only":     (("f7",), None, None),       # F7 単独 (P1 無し)
    **{("f7_ex_%x" % s): (("f7", "p1"), {s}, None) for s in F7_SITES},
    "p1_env":      (("f7", "p1"), None, set(P1_ENV)),
    "p1_tail":     (("f7", "p1"), None, set(P1_TAIL)),
    "p1_resume":   (("f7", "p1"), None, {0x1801209BB}),
    "p1_cvt":      (("f7", "p1"), None, {0x1801BCA83, 0x1801BD1D7}),
    "p1_tanpoly":  (("f7", "p1"), None, {0x1801AA108}),
    "p1_only":     (("p1",), None, None),      # 参考測定 (production は F7 先行なので非 production 構成)
}
# p1_one_<va>: P1 の再構成を 1 site だけに絞る (脱落分岐 site の個別評価 / 無限ルーブリーションの切り分け用)
for _s in P1_ENV + P1_TAIL + [0x1801209BB, 0x1801AA108, 0x1801B4277, 0x1801BCA83, 0x1801BD1D7]:
    VARIANTS["p1_one_%x" % _s] = (("f7", "p1"), None, {_s})


def _fn_names(recs, fn, fm):
    """脱落分岐 site を関数 VA に対応付ける (P1_FNMAP=1 の診断用)。"""
    m = re.match(r"function_([0-9a-f]+)$", fn.name)
    fva = int(m.group(1), 16) if m else None
    for rec in recs:
        fm["A%x" % rec["A"]] = fva
        for c in rec["consumers"]:
            fm["J%x" % c["J"]] = fva

FNMAP = {}                                    # "A<va>"/"J<va>" -> 関数 va (P1_FNMAP=1 で記録)


def install_filters(f7_exclude, p1_allow):
    from liftlib.passes import f7 as F7, p1 as P1
    if f7_exclude is not None:
        def scan(mod, fn, mf, binder, _o=F7.scan, _ex=f7_exclude):
            return [c for c in _o(mod, fn, mf, binder) if c[0] not in _ex]
        F7.scan = scan
    if p1_allow is not None or os.environ.get("P1_FNMAP"):
        def analyze(mod, fn, mf, binder, _o=P1.analyze, _al=p1_allow):
            sites = _o(mod, fn, mf, binder)
            if os.environ.get("P1_FNMAP"):
                m = re.match(r"function_([0-9a-f]+)$", fn.name)
                fva = int(m.group(1), 16) if m else None
                for rec in sites:
                    FNMAP["A%x" % rec["A"]] = fva
                    for c in rec["consumers"]:
                        FNMAP["J%x" % c["J"]] = fva
            if _al is not None:
                for rec in sites:
                    rec["consumers"] = [c for c in rec["consumers"]
                                        if c.get("state") in ("branch", "region_done", "unsupported")
                                        or c["J"] in _al]
            return sites
        P1.analyze = analyze


def find_node():
    """node を解決 (PATH 無し環境では emsdk 同梱 node を使う — ott_e2e.sh と同じ規約)。"""
    n = shutil.which("node")
    if n:
        return n
    c = sorted(glob.glob("/opt/emsdk/node/*/bin/node"))
    return c[-1] if c else "node"


NODE = find_node()


def node_run(args, env_extra=None, timeout=1200):
    e = dict(os.environ)
    if env_extra:
        e.update(env_extra)
    r = subprocess.run([NODE] + args, capture_output=True, text=True, env=e, timeout=timeout, cwd=PKG)
    return r.returncode, r.stdout + r.stderr


def light_e2e(cjs):
    """e2e_check (checks/census) + trap10 + bitcmp (vs tools/ott x64c 参照) を実行して dict で返す。"""
    res = {}
    rc, txt = node_run(["liftlib/recipes/ott/e2e_check.mjs"], {"OTT_CJS": os.path.abspath(cjs)})
    m = re.search(r"checks (\d+) / broken (\d+)", txt)
    res["checks"], res["broken"] = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    m0 = re.search(r"census \[0x248\]=0 : (\{.*\})", txt)
    m1 = re.search(r"census \[0x248\]=1 : (\{.*\})", txt)
    res["census0"] = json.loads(m0.group(1)) if m0 else None
    res["census1"] = json.loads(m1.group(1)) if m1 else None
    rc2, _ = node_run(["liftlib/recipes/ott/e2e_trap10.mjs"], {"OTT_CJS": os.path.abspath(cjs)})
    res["trap_rc"] = rc2
    ref = os.path.join(OTT, "work", "lift", "ottl.cjs")
    if os.path.exists(ref):
        rc3, txt3 = node_run([os.path.join(HERE, "cab238_bitcmp.mjs")],
                             {"MOD_A": os.path.abspath(cjs), "MOD_B": ref}, timeout=1200)
        summary = [l for l in txt3.splitlines() if l.startswith("SUMMARY ")]
        res["bitcmp_vs_x64c"] = json.loads(summary[-1][8:]) if summary else {"error": txt3[-300:]}
        res["bitcmp_rc"] = rc3
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--reuse", action="store_true",
                    help="既存 build (OUT/<tag>/ott_gen.cjs) を再利用し light_e2e (bitcmp 含む) のみ再実行する")
    a = ap.parse_args()
    if a.tag not in VARIANTS:
        print("[eval] unknown tag %s" % a.tag)
        return 2
    auto, f7_ex, p1_al = VARIANTS[a.tag]
    W = os.path.join(OUT, a.tag)
    os.makedirs(W, exist_ok=True)
    if a.reuse:
        cjs = os.path.join(W, "ott_gen.cjs")
        if not os.path.exists(cjs):
            print("[eval] %s: --reuse だが %s が無い" % (a.tag, cjs))
            return 2
        pj = os.path.join(W, "result.json")
        out = json.load(open(pj)) if os.path.exists(pj) else {"tag": a.tag}
        out.update(light_e2e(cjs))
        with open(pj, "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        print("[eval] %s (reuse): checks %s/%s census0.junkHi=%s bitcmp=%s" % (
            a.tag, out.get("checks"), out.get("broken"),
            (out.get("census0") or {}).get("junkHi"), json.dumps(out.get("bitcmp_vs_x64c"))))
        return 0
    install_filters(f7_ex, p1_al)
    from liftlib.recipes import ott
    try:
        res, log = ott.run(W, build=True, helpers="gen", auto=auto, lb_base=None)
    except Exception as ex:                    # noqa
        out = {"tag": a.tag, "auto": list(auto), "f7_exclude": sorted(f7_ex) if f7_ex else None,
               "p1_allow": ["%x" % x for x in sorted(p1_al)] if p1_al else None,
               "error": "%s: %s" % (type(ex).__name__, str(ex)[:600])}
        with open(os.path.join(W, "result.json"), "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        print("[eval] %s: ERROR %s" % (a.tag, out["error"][:160]))
        return 1
    out = {"tag": a.tag, "auto": list(auto), "f7_exclude": sorted(f7_ex) if f7_ex else None,
           "p1_allow": ["%x" % x for x in sorted(p1_al)] if p1_al else None,
           "auto_stats": res.get("auto_stats"), "link": res.get("link_warnings")}
    out.update(light_e2e(res["cjs"]))
    # `P1_HANG_PROBE=1` で outhash の無限ループ combo (params=0.9 / [0x248]=1) を併せて測定する
    if os.environ.get("P1_HANG_PROBE"):
        hp = {}
        for amp in ("0.0", "1.0"):
            env = dict(os.environ, V="0.9", A=amp, F="1",
                       OTT_CJS=os.path.abspath(res["cjs"]))
            try:
                r = subprocess.run([NODE, os.path.join(HERE, "cab238_bitcmp.mjs").replace("bitcmp", "probe")],
                                   capture_output=True, text=True, env=env, timeout=60)
                hp[amp] = r.returncode
            except subprocess.TimeoutExpired:
                hp[amp] = "HANG"
        out["hang_p0.9_f1"] = hp
    with open(os.path.join(W, "result.json"), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    if FNMAP:
        json.dump(FNMAP, open(os.path.join(OUT, "p1_site_functions.json"), "w"), indent=1, sort_keys=True)
    print("[eval] %s: checks %s/%s census0.junkHi=%s bitcmp=%s" % (
        a.tag, out.get("checks"), out.get("broken"),
        (out.get("census0") or {}).get("junkHi"), json.dumps(out.get("bitcmp_vs_x64c"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
