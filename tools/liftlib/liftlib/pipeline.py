"""pipeline.py — 設定 JSON 駆動の lift 修復パイプライン (lift → 修復 → helper 生成 → emcc)。

cfg (JSON) の主なキー:
  name, image, funcs: ["function_180afe090"]  (module 内で修復対象にする関数; 省略時は全て)
  raw_ll (既存の RetDec raw .ll; 無ければ retdec.ranges で RetDec 実行)
  retdec: {"ranges": "0x..-0x..,...", "timeout": 900}
  passes: {"p1": true, "f7": true, "f2": true, "gdata": "external"|"all"|null, "shift": {"base":..,"newbase":..}|null}
  exports: [ "function_180afe090", ... ]
  extra_funcs: [["0x1802f7370", "0x1802f74ec"], ...]  (.pdata 外の leaf 関数を合成エントリ登録。p1/f2 が機械語を参照するため)
  emcc: {"opt": "-O1" (profile dev のみ), "extra": [..], "variant_extra": {"<変種名>": [..]} (署名ガード変種ごとの追加フラグ), "sources": [..] (追加 C)}
  spec / wasm_func / signature: {"n": 署名用シナリオ数, "expect": 期待署名} (標準ビルド `build` の署名ガード用)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import env
from . import ir as IR
from . import stdbuild as SB
from .pe import Image
from .passes import base as B, p1, f7, f2, iargs, remap
from .passes import icall as ICALL
from .simd import gen as SG

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HERE = os.path.abspath(os.path.dirname(__file__))
SIMD_DIR = os.path.join(HERE, "simd")


def rpath(p):
    """repo 相対 / 絶対パス。`${PLUGINS_DIR}` 等 (env.PATH_VARS のキー) は環境変数優先で展開する"""
    if p is None:
        return None
    p = re.sub(r"\$\{(\w+)\}", lambda m: env.PATH_VARS[m.group(1)], p)
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_cfg(path):
    cfg = json.load(open(path))
    cfg["_path"] = os.path.abspath(path)
    return cfg


def retdec_lift(cfg, workdir, log):
    """RetDec --select-ranges で raw .ll を生成 (既存 raw_ll があればそれを使う)。"""
    if cfg.get("raw_ll"):
        return rpath(cfg["raw_ll"])
    rd = cfg["retdec"]
    out_c = os.path.join(workdir, cfg["name"] + ".drc.c")
    out_ll = os.path.join(workdir, cfg["name"] + ".drc.ll")
    if os.path.exists(out_ll) and not cfg.get("force_lift"):
        log.append("retdec: reuse %s" % out_ll)
        return out_ll
    tmp = os.path.join(workdir, "tmp")
    os.makedirs(tmp, exist_ok=True)
    e = dict(os.environ, TMPDIR=tmp)
    cmd = ["/opt/retdec/bin/retdec-decompiler", rpath(cfg["image"]), "-o", out_c, "--select-ranges", rd["ranges"],
           "--select-decode-only", "--timeout", str(rd.get("timeout", 1800))]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=e)
    log.append("retdec: %.1fs rc=%d" % (time.time() - t0, r.returncode))
    if not os.path.exists(out_ll):
        raise RuntimeError("RetDec failed: " + (r.stdout + r.stderr)[-1500:])
    dsm = os.path.join(workdir, cfg["name"] + ".drc.dsm")
    if os.path.exists(dsm) and not cfg.get("keep_dsm"):
        os.remove(dsm)
    return out_ll


def repair_ll(cfg, raw_path, img, log, detect_only=False):
    """raw .ll → 修復済み Module。返値 (Module, stats)

    LIFTLIB-5: leaf cfg (passes.leafabi を持つ) のときだけ mc.LEAF_EXT を有効にする (tan/SVF 用の
    call preserve / GPR spill / setcc i1 / 多定義 def 限定 / ret・RX phi)。FA/KH/OTT 既定は不変。"""
    from . import mc as _mc
    prev = _mc.LEAF_EXT
    _mc.LEAF_EXT = bool(cfg.get("passes", {}).get("leafabi"))
    try:
        return _repair_ll(cfg, raw_path, img, log, detect_only)
    finally:
        _mc.LEAF_EXT = prev


def _repair_ll(cfg, raw_path, img, log, detect_only=False):
    stats = {}
    t0 = time.time()
    text, brep = B.run_base(open(raw_path).read(), B.make_args())
    stats["base"] = {k: v for k, v in brep.items() if k in ("b1_fixed", "s1_stores", "a9_residual_constexpr", "fixups_add0", "dup_declares_removed")}
    passes = cfg.get("passes", {})
    if (passes.get("icall") or {}).get("blk_global"):
        import json as _json
        blk = _json.load(open(os.path.join(os.path.dirname(raw_path), cfg["name"] + ".icall.map.json")))["blk"]
        text, nblk = ICALL.blk_global_text(text, blk)
        stats["icall_blk_global"] = nblk
        log.append("icall.blk_global: %d refs -> @__icall_blk (blk %#x)" % (nblk, blk))
    mod = IR.Module.parse(text)
    names = set(cfg.get("funcs") or [f.name for f in mod.funcs()])
    rep = not detect_only
    # LIFTLIB-2: f2 を p1 より前に実行する (callee 相で入口 xmm 値 (%xmmK_bits 引数) を
    # define に足し, callsite 相で生存側 call を固定した後に p1 が領域を lift する。
    # p1 の領域は _lift_call で f2 済みの declare 引数 (%xmmK_bits) を正しく渡し,
    # f2 の bind は領域コピーが存在しない素な IR に対して行われる (支配違反の混入を避ける)。
    # HB-H3: 整数引数 (rdx/r8/r9) 脱落の復元は f2 より前 (f2 は仮引数末尾に %xmmK_bits を足す)。既定 off。
    if passes.get("iargs"):
        st, lg = {}, []
        iargs.run(mod, img, lg, st, repair=rep)
        stats["iargs"] = st
        log.extend("iargs: " + x for x in lg)
    if passes.get("f2", True):
        st, lg = {}, []
        f2.run(mod, img, lg, st, repair=rep, only=passes.get("f2_only"), phase="callee")
        stats["f2_callee"] = st
        log.extend("f2: " + x for x in lg)
        st, lg = {}, []
        f2.run(mod, img, lg, st, repair=rep, only=passes.get("f2_only"), phase="callsite")
        stats["f2"] = st
        log.extend("f2: " + x for x in lg)
    if passes.get("p1", True):
        st, lg = {}, []
        for fn in mod.funcs():
            if fn.name in names:
                p1.run_function(mod, fn, img, rep, lg, st)
        stats["p1"] = st
        log.extend("p1: " + x for x in lg)
    if passes.get("f7", True):
        st, lg = {}, []
        for fn in mod.funcs():
            if fn.name in names:
                f7.run_function(mod, fn, img, rep, lg, st)
        stats["f7"] = st
        log.extend("f7: " + x for x in lg)
    if passes.get("leafabi") and not detect_only:
        from .passes import leafabi as LA
        st, lg = {}, []
        LA.run(mod, img, passes["leafabi"].get("ret_xmm0", []), lg, st, repair=rep)
        stats["leafabi"] = st
        log.extend("leafabi: " + x for x in lg)
    if passes.get("gdata") and not detect_only:
        sh = passes.get("shift")
        if sh:
            text2, n = remap.shift_va(mod.dump(), int(str(sh["base"]), 0), int(str(sh["newbase"]), 0),
                                      add_forms=bool(sh.get("add_forms")))
            mod = IR.Module.parse(text2)
            stats["shift_numeric"] = n
        stats["gdata"] = remap.gdata(mod, img, mode=passes["gdata"], base=img.base,
                                     newbase=int(str(passes["shift"]["newbase"]), 0) if passes.get("shift") else None,
                                     pad_gap=bool(cfg.get("gdata_pad")))
    stats["time_s"] = round(time.time() - t0, 2)
    return mod, stats


def c_ty(t):
    t = t.strip().split()[0]
    return {"i64": "long long", "i32": "int", "i16": "short", "i8": "signed char", "ptr": "void*", "i128": "unsigned __int128",
            "double": "double", "float": "float", "void": "void", "i1": "_Bool"}.get(t, "long long")


def emit_stubs(mod, defined_extra=(), externals=False):
    """define の無い declare を fail-fast stub 化 (function_* は常時, externals=True で
    Win32/CRT 等も対象 — llvm.*/__asm_*/_emscripten 系は除外)。"""
    defs = {f.name for f in mod.funcs()}
    lines = ['#include <emscripten.h>', '/* liftlib auto stubs: 未 lift の callee は fail-fast (黙って 0 を返さない) */']
    n = 0
    for nm, (ret, args, _l) in sorted(mod.declares().items()):
        if nm in defs or nm in defined_extra:
            continue
        if re.match(r"function_[0-9a-f]+$", nm):
            pass
        elif not externals or nm.startswith("__asm_") or nm.startswith("llvm.") or nm.startswith("_emscripten") \
                or nm.startswith("__cxa") or nm.startswith("_ZN") or nm.startswith("_Z"):
            continue
        else:
            pass
        al = [a.strip() for a in args.split(",") if a.strip()]
        params = ", ".join("%s a%d" % (c_ty(a), i) for i, a in enumerate(al)) or "void"
        rt = c_ty(ret)
        lines.append('EMSCRIPTEN_KEEPALIVE %s %s(%s) { __builtin_trap(); %s}' % (rt, nm, params, "" if rt == "void" else "return 0; "))
        n += 1
    return "\n".join(lines) + "\n", n


def icall_table_c(mod):
    """#2128: 引数無し i64 define の VA→関数 表 (icall_tbl_va/fn/n) と cfg 表を C で出す。
    __icall_dispatch (tools/icall/rt/icall_rt.c) が参照する。返値 (C 文字列, 登録数)。"""
    ents = []
    for f in mod.funcs():
        m = re.match(r"function_([0-9a-f]+)$", f.name)
        if m and not f.params() and f.ret_type() == "i64":
            ents.append((int(m.group(1), 16), f.name))
    ents.sort()
    lines = ["/* liftlib icall table (#2128): 引数無し i64 関数のみ。BLK 経由の引数付き関数は対象外 */",
             "#include <stdint.h>"]
    for _, nm in ents:
        lines.append("extern long long %s(void);" % nm)
    lines.append("const uint32_t icall_tbl_va[] = {%s};" % ",".join(["0x%xu" % va for va, _ in ents] or ["0"]))
    lines.append("long long (*const icall_tbl_fn[])(void) = {%s};" % ",".join([nm for _, nm in ents] or ["0"]))
    lines.append("const unsigned icall_tbl_n = %d;" % len(ents))
    lines.append("const uint32_t icall_cfg_va[] = {0};")
    lines.append("const unsigned icall_cfg_n = 0;")
    return "\n".join(lines) + "\n", len(ents)


def prepare(cfg, mod, workdir, stats):
    """修復済み Module → 正規名 IR + SIMD helper C + stub C を書く (変種に依らず 1 回)。返値 (ll_path, h_path, s_path)"""
    name = cfg["name"]
    text = mod.dump()
    decls = SG.scan_decls(text)           # 正規化前の宣言から取る (正規化後に読むと ptr 引数の名前が二重に正規化される)
    text, mp = SG.canonicalize(text)
    ll_path = os.path.join(workdir, name + "_fixed.ll")
    open(ll_path, "w").write(text)
    c, rep = SG.emit_c(decls, use_names="canon")
    h_path = os.path.join(workdir, name + "_simd.c")
    open(h_path, "w").write(c)
    stats["simd"] = {"helpers": len(rep["generated"]), "unsupported": [u[0] for u in rep["unsupported"]], "approx": rep["approx"]}
    mod2 = IR.Module.parse(text)
    ex = set(cfg.get("stub_skip", []))
    if (cfg.get("passes", {}).get("icall") or {}).get("blk_global"):
        ex |= {"__icall_dispatch", "__icall_comis"}   # #2128: runtime (icall_rt.c) が定義する
    stub_c, nstub = emit_stubs(mod2, ex, externals=bool(cfg.get("stub_externals")))
    if (cfg.get("passes", {}).get("icall") or {}).get("blk_global"):
        tbl_c, ntbl = icall_table_c(mod2)
        stub_c += tbl_c
        stats["icall_tbl"] = ntbl
    s_path = os.path.join(workdir, name + "_stubs.c")
    open(s_path, "w").write(stub_c)
    stats["stubs"] = nstub
    return ll_path, h_path, s_path


def lb_link_flags(cfg):
    """cfg.emcc.lb_layout (opt-in) があるとき lowbase の linear memory レイアウトを emcc のリンクフラグにする。
    値: {"newbase": V-shift 先 LB_BASE, "init_mib": 省略時 GLOBAL_BASE から自動算出, "max_mib": 既定 64}。
    規約は recipes/ott.py と同じ (-sINITIAL_MEMORY/-sMAXIMUM_MEMORY。lb_layout.layout が正本)。
    未指定なら [] (既存 leaf の出力は不変)。"""
    lb = cfg.get("emcc", {}).get("lb_layout")
    if not lb:
        return []
    from . import lb_layout
    img = Image(rpath(cfg["image"]))
    base = int(str(lb["newbase"]), 0)
    arena0 = lb_layout.up(base + img.size, 0x10000)
    gb0 = lb_layout.up(arena0 + 0x100000, 0x10000)
    init_mib = lb.get("init_mib") or max(24, (gb0 >> 20) + 17)
    L = lb_layout.layout(base=base, image_size=img.size, arena_size=0x100000, init_mib=init_mib,
                         max_mib=max(lb.get("max_mib", 64), init_mib))
    return ["-sGLOBAL_BASE=%d" % L["LB_GLOBAL_BASE"], "-sINITIAL_MEMORY=%d" % L["LB_INIT"],
            "-sMAXIMUM_MEMORY=%d" % L["LB_MAX"]]


def emit(cfg, paths, workdir, profile="dev", tag=None):
    """prepare の出力 → emcc → <name>[.<tag>].cjs。profile は data/std_build.json (標準 = std)。
    dev (既定・後方互換) だけ cfg の emcc.opt を尊重する (旧 -O1)。それ以外は profile が最適化水準を決める。"""
    ll_path, h_path, s_path = paths
    name = cfg["name"]
    em = cfg.get("emcc", {})
    exports = ["_malloc", "_free"] + ["_" + e for e in cfg.get("exports", [])]
    out_js = os.path.join(workdir, name + (("." + tag) if tag else "") + ".js")
    fl = SB.flags(profile, rounding_math=True)
    if profile == "dev" and em.get("opt"):
        fl = [em["opt"] if f == "-O1" else f for f in fl]
    cmd = (["emcc", "-w"] + fl + ["-I", SIMD_DIR, ll_path, h_path, s_path] + [rpath(x) for x in em.get("sources", [])] + em.get("extra", [])
           + (em.get("variant_extra", {}).get(tag, []) if tag else [])
           + ["-sERROR_ON_UNDEFINED_SYMBOLS=1", "-sMODULARIZE=1", "-sENVIRONMENT=node", "-sALLOW_MEMORY_GROWTH=1",
              "-sEXPORTED_FUNCTIONS=" + ",".join(exports), "-sEXPORTED_RUNTIME_METHODS=HEAPU8", "--no-entry", "-o", out_js])
    cmd += lb_link_flags(cfg)
    bad = SB.violations(profile, cmd)
    if bad:
        raise SB.StdBuildError("profile %s に禁止フラグ: %s" % (profile, " ".join(bad)))
    r = env.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("emcc failed (%s):\n%s" % (profile, r.stderr[-3000:]))
    cjs = out_js[:-3] + ".cjs"
    os.replace(out_js, cjs)
    return cjs


def build(cfg, mod, workdir, log, stats, profile="dev"):
    """修復済み Module → helper 生成 → emcc → <name>.cjs (単一 profile。署名ガード無し = 旧 lift 経路)"""
    paths = prepare(cfg, mod, workdir, stats)
    return emit(cfg, paths, workdir, profile), paths[0]


def build_variants(cfg, mod, workdir, log, stats, profile="std", variants=None, n=None, expect=None, timeout=300):
    """標準ビルド入口: 1 回の修復結果から profile + 署名ガード変種を全部ビルドし、wasm_runner 署名が全一致のときだけ
    <name>.cjs (= profile 版) を確定する。不一致 / 期待署名違いは SignatureMismatch (成果物 <name>.cjs は作らない)。
    変種名は `<tag>` (= profile 名) か `<tag>=<profile>` (variant_extra[tag] で追加フラグを足す変種)。
    署名 = 同一シナリオ (cfg.spec; 実機 oracle 不要) を各変種の wasm に流した出力の正規化ハッシュ (stdbuild.canon_digest)。"""
    from .harness import diff as D, spec as SP
    spec = json.load(open(os.path.join(HERE, "..", cfg["spec"])))
    paths = prepare(cfg, mod, workdir, stats)
    names = list(dict.fromkeys(list(variants if variants is not None else SB.load()["guard_variants"]) + [profile]))
    scen = os.path.join(workdir, "sigguard_scen.txt")
    open(scen, "w").write(SP.build(spec, n=n))
    sigp = os.path.join(workdir, "sigguard_sig.json")
    json.dump(D.wasm_sig(paths[0], cfg["wasm_func"]), open(sigp, "w"))
    final = os.path.join(workdir, cfg["name"] + ".cjs")
    if os.path.exists(final):
        os.remove(final)
    res = {}
    for v in names:
        t0 = time.time()
        cjs = emit(cfg, paths, workdir, v.partition("=")[2] or v, tag=v.partition("=")[0])
        t_build = time.time() - t0
        outp = os.path.join(workdir, "sigguard_out_%s.txt" % v)
        t0 = time.time()
        if D.run_wasm(cjs, cfg["wasm_func"], sigp, scen, outp, timeout) is None:
            sig = "TIMEOUT"
        else:
            try:
                sig = SB.canon_digest(open(outp).read(), spec)
            except SB.StdBuildError as e:
                sig = "NO-RESULT"
                log.append("stdbuild: %s %s" % (v, e))
        res[v] = dict(cjs=cjs, wasm_bytes=os.path.getsize(cjs[:-4] + ".wasm"), build_s=round(t_build, 2), run_s=round(time.time() - t0, 2),
                      sig=sig)
        log.append("stdbuild: %s %dB build %.1fs sig %s" % (v, res[v]["wasm_bytes"], t_build, res[v]["sig"]))
    rep = dict(variants=res, profile=profile)
    try:
        rep["guard"] = SB.guard({k: v["sig"] for k, v in res.items()}, expect)
    except SB.SignatureMismatch:
        json.dump(rep, open(os.path.join(workdir, cfg["name"] + ".sig.json"), "w"), indent=1, default=str)
        raise
    shutil.copyfile(res[profile]["cjs"], final)
    shutil.copyfile(res[profile]["cjs"][:-4] + ".wasm", final[:-4] + ".wasm")
    json.dump(rep, open(os.path.join(workdir, cfg["name"] + ".sig.json"), "w"), indent=1, default=str)
    return final, rep


def lift_repair(cfg_path, workdir=None, detect_only=False):
    """設定 JSON → RetDec → 修復 pass。返値 (cfg, workdir, mod, stats, log)。ビルドはしない"""
    cfg = load_cfg(cfg_path)
    workdir = workdir or os.path.join(HERE, "..", "work", cfg["name"])
    workdir = os.path.abspath(workdir)
    os.makedirs(workdir, exist_ok=True)
    log, stats = [], {}
    img = Image(rpath(cfg["image"]))
    for b, e in cfg.get("extra_funcs", []):
        img.add_func(int(str(b), 0), int(str(e), 0))
    ic = cfg.get("passes", {}).get("icall")
    if ic:   # lift 前に PE を書換え (間接 call/jmp 復元 + ABI 仮想化 + D7 回避)。img (修復 pass が参照する正本) は元 PE のまま
        rimg, rranges, icmap = ICALL.prelift(cfg, rpath(cfg["image"]), rpath(ic["funcs"]), workdir, log)
        cfg = dict(cfg, image=rimg, retdec=dict(cfg.get("retdec", {}), ranges=rranges))
        raw = retdec_lift(cfg, workdir, log)
        raw = ICALL.restore(raw, icmap, workdir, log)
        cfg["raw_ll"] = raw
    else:
        raw = retdec_lift(cfg, workdir, log)
    mod, st = repair_ll(cfg, raw, img, log, detect_only=detect_only)
    stats.update(st)
    return cfg, workdir, mod, stats, log


def _dump_report(workdir, stats, log):
    json.dump(dict(stats=stats, log=log), open(os.path.join(workdir, "pipeline_report.json"), "w"), indent=1, ensure_ascii=False, default=str)


def run_all(cfg_path, workdir=None, detect_only=False):
    cfg, workdir, mod, stats, log = lift_repair(cfg_path, workdir, detect_only)
    cjs = None
    if not detect_only:
        cjs, ll_path = build(cfg, mod, workdir, log, stats)
    _dump_report(workdir, stats, log)
    return cfg, workdir, cjs, stats, log


def run_build(cfg_path, workdir=None, profile="std", variants=None, n=None, expect=None, timeout=300):
    """標準ビルド入口 (`python3 -m liftlib build`)。lift → 修復 → profile ビルド + 署名ガード。
    返値 (cfg, workdir, cjs, stats, log, rep)。署名不一致は SignatureMismatch (rep は <name>.sig.json に残る)。"""
    cfg, workdir, mod, stats, log = lift_repair(cfg_path, workdir)
    sg = cfg.get("signature", {})
    try:
        cjs, rep = build_variants(cfg, mod, workdir, log, stats, profile=profile, variants=variants,
                                  n=n or sg.get("n"), expect=expect or sg.get("expect"), timeout=timeout)
    finally:
        _dump_report(workdir, stats, log)
    return cfg, workdir, cjs, stats, log, rep
