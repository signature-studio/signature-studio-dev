"""ott.py — OTT (Xfer OTT VST2 win64) を liftlib 側だけで再現する recipe driver (m10_e2e.sh 相当)。

  汎用 pass (liftlib 実装)      : base 正規化 (m2+m5) / P1(legacy 配線) / VA shift / gdata / data image / SIMD helper 自動生成
  OTT 固有 recipe (vendored 無改変): memfix / full_extract / argpass_fixed / valueflow / bootstraps / outcopy (recipes/ott/)
  入力 (既存 dir の成果物, 読取のみ): tools/m6/work/{ott.drc.ll, full_t1.drc.{ll,dsm}, m6_stubs*.c}, runtime C (m6_rt/m8_rt/m9_rt/m10_boot), shim heap

各段で「元のチェーンの中間成果物とテキスト一致するか」を記録する (pass 単位の IR diff 検証)。
"""
import json
import os
import re
import subprocess
import sys
import time

from .. import env, ir as IR, lb_layout, runtime_lb
from ..pe import Image
from ..passes import base as B, p1_legacy, remap, dataimage
from ..simd import gen as SG

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
TOOLS = os.path.join(ROOT, "tools")
M6, M8, M9, M10 = (os.path.join(TOOLS, x) for x in ("m6", "m8", "m9", "m10"))
RECIPES = os.path.join(HERE, "ott")
DLL = env.OTT_DLL
SIMD_DIR = os.path.join(HERE, "..", "simd")


def nb(text):
    return [l for l in text.split("\n") if l.strip()]


def resolve_layout(img, lb_base, init_mib=None, max_mib=64):
    """CAB-220: 全レイアウト定数を LB_* 変数に統一。

    - 既定 (lb_base=None / 0x30000000) は元 m10 chain のレイアウトを LB_* で表現したもの
      (GLOBAL_BASE=256MiB の hole / initial=max=864MiB / arena は image 直後の 64K 境界) —
      emcc フラグ・出力とも旧ビルドと同一 (回帰 = IR 一致 + outhash 42/42 で確認)。
    - それ以外は lb_layout.layout() (tools/hostbridge/lowbase と共有の定義) に従う。
      init_mib 未指定時は GLOBAL_BASE + stack 8MB + 余裕から自動算出する
      (wasm-ld の required 実測: base=0x1230000 で 31,089,728B = GLOBAL_BASE 23.25MiB + stack/static 約 8.9MiB)。
    """
    if lb_base in (None, 0x30000000):
        arena = lb_layout.up(img.base + img.size, 0x10000)
        return dict(LB_BASE=0x30000000, LB_ARENA=arena, LB_GLOBAL_BASE=0x10000000,
                    LB_INIT=0x36000000, LB_MAX=0x36000000, legacy=True)
    arena0 = lb_layout.up(lb_base + img.size, 0x10000)
    gb0 = lb_layout.up(arena0 + 0x100000, 0x10000)
    init_mib = init_mib or max(24, (gb0 >> 20) + 17)
    lay = lb_layout.layout(base=lb_base, image_size=img.size, arena_size=0x100000,
                           init_mib=init_mib, max_mib=max_mib)
    return dict(LB_BASE=lay["LB_BASE"], LB_ARENA=lay["LB_ARENA"], LB_GLOBAL_BASE=lay["LB_GLOBAL_BASE"],
                LB_INIT=lay["LB_INIT"], LB_MAX=lay["LB_MAX"], legacy=False)


def same(text, ref_path):
    if not os.path.exists(ref_path):
        return None
    # p1 の一時名 %pc<行 index> は空行数に依る (#1664 以降の入力では名前だけが変わる)。改名だけを無視する (#2863)
    return nb(p1_legacy.canon_tags(text)) == nb(p1_legacy.canon_tags(open(ref_path).read()))


def sh(cmd, cwd, log, name):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    log.append("%s: rc=%d %.1fs" % (name, r.returncode, time.time() - t0))
    if r.returncode:
        raise RuntimeError("%s failed:\n%s\n%s" % (name, r.stdout[-1500:], r.stderr[-1500:]))
    return r


def run(workdir, build=True, helpers="gen", auto=(), lb_base=None):
    W = os.path.abspath(workdir)
    os.makedirs(os.path.join(W, "work"), exist_ok=True)
    log, res = [], {}
    img = Image(DLL)
    L = resolve_layout(img, lb_base)
    LB = L["LB_BASE"]
    res["lb"] = {k: (hex(v) if isinstance(v, int) else v) for k, v in L.items()}
    legacy = L["legacy"]
    for f in ("full_t1.drc.ll", "full_t1.drc.dsm"):
        dst = os.path.join(W, "work", f)
        if os.path.islink(dst) and not os.path.exists(dst):   # 素材同梱の壊れた symlink (VM の絶対パス) は張り直す
            os.remove(dst)
        if not os.path.exists(dst):
            os.symlink(os.path.join(M6, "work", f), dst)
    # ---- O1 base 正規化
    t0 = time.time()
    raw = open(os.path.join(M6, "work", "ott.drc.ll")).read()
    text, brep = B.run_base(raw, B.make_args())
    mod0 = IR.Module.parse(text)
    if auto:
        from ..passes import f7 as F7, p1 as P1, f2 as F2
        st_a, lg_a = {}, []
        # LIFTLIB-3: f2 の callee 相を auto の先頭に入れる。CRT leaf (exp/log/tan 系) が
        # 入口 xmm を読むのに IR 側に値が無く p1 の dropped 領域で `bind xmm0/xmm1` が
        # 失敗していた (残留 21 の主因)。%xmmK_bits 引数を先に足しておくことで
        # 残留 21 → 15, bind xmm0 6 → 1 に減る (実測 xmm0_ret_census.py / dbg_reason.py)。
        # callsite 相は recipe 側の名前依存 wiring (m9_d* C port) と衝突するため既定では
        # 入れない (--auto f2 で明示指定時のみ有効)。
        if "f2" in auto:
            F2.run(mod0, img, lg_a, st_a, phase="callee")
            st_a, lg_a = {}, []
        for fn in mod0.funcs():
            if "f7" in auto:
                F7.run_function(mod0, fn, img, True, lg_a, st_a)
            if "p1" in auto:
                P1.run_function(mod0, fn, img, True, lg_a, st_a)
        res["auto_stats"] = st_a
        open(os.path.join(W, "auto_repair.log"), "w").write("\n".join(lg_a))
    lift = mod0.dump(strip=True)
    open(os.path.join(W, "ott_lift.ll"), "w").write(lift)
    res["O1_base_identical_to_m6_ott_lift"] = same(lift, os.path.join(M6, "work", "ott_lift.ll")) if not auto and legacy else None
    log.append("O1 base: %.1fs b1=%s a9res=%s" % (time.time() - t0, brep.get("b1_fixed"), brep.get("a9_residual_constexpr")))
    # ---- O2 P1(legacy 配線) → VA shift (newbase=LB_BASE, CAB-220) → gdata
    p1t, st = p1_legacy.legacy_p1(lift)
    res["O2a_p1_identical"] = same(p1t, os.path.join(M6, "work", "ir7e_p1.ll")) if legacy else None
    res["p1_stats"] = st
    # maxv は image 範囲 (base+SizeOfImage) から導出 (lowbase integration.md §A)。
    # 既定 0x1803FFFFF は元 ir6_shift の値 (legacy 回帰のテキスト一致維持のためそのまま)。
    sht, nnum = remap.shift_va(p1t) if legacy else remap.shift_va(p1t, newbase=LB, maxv=img.base + img.size)
    res["O2b_shift_identical"] = same(sht, os.path.join(M6, "work", "ir7e_p2.ll")) if legacy else None
    gdt, gst = remap.gdata_legacy(sht, img, datab=LB)
    open(os.path.join(W, "ott_shift3b.ll"), "w").write(gdt)
    res["O2c_gdata_identical"] = same(gdt, os.path.join(M6, "work", "ir7e_p3.ll")) if legacy else None
    res["gdata"] = gst
    # ---- O3 memfix / full_extract (vendored recipes)
    sh([sys.executable, os.path.join(RECIPES, "m6_memfix.py"), "ott_shift3b.ll", "work/ott_memfix0.ll"], W, log, "memfix")
    res["O3a_memfix0_identical"] = same(open(os.path.join(W, "work/ott_memfix0.ll")).read(), os.path.join(M6, "work", "ott_memfix0.ll")) if legacy else None
    sh([sys.executable, os.path.join(RECIPES, "m6_full_extract.py"), "work/ott_memfix1.ll",
        "function_1801260c0", "function_180126030", "function_180126010", "--newbase", str(LB)], W, log, "full_extract")
    res["O3b_memfix1_identical"] = same(open(os.path.join(W, "work/ott_memfix1.ll")).read(), os.path.join(M6, "work", "ott_memfix1.ll")) if legacy else None
    # ---- O4 m8/m9 recipes
    sh([sys.executable, os.path.join(RECIPES, "ir7_argpass_fixed.py"), "work/ott_memfix1.ll", "work/ott_argpass8.ll",
        "--dsm", "work/full_t1.drc.dsm", "--report", "work/argpass8.json", "--target", "function_180120af0",
        "--tail", "function_18011de50", "--shift", str(LB)], W, log, "argpass")
    sh([sys.executable, os.path.join(RECIPES, "ir8_valueflow.py"), "work/ott_argpass8.ll", "work/ott_m8.ll", "--dsm", "work/full_t1.drc.dsm",
        "--full-ir", "work/full_t1.drc.ll", "--report", "work/valueflow.json", "--targets", "function_180126030"], W, log, "valueflow")
    sh([sys.executable, os.path.join(RECIPES, "ir9_bootstraps.py"), "work/ott_m8.ll", "work/ott_m10.ll", "--dsm", "work/full_t1.drc.dsm",
        "--report", "work/bootstraps.json", "--newbase", str(LB)], W, log, "bootstraps")
    if "f7" not in auto:        # 汎用 F7 (passes/f7.py) が outcopy を包含するため, auto=f7 のときは省略
        sh([sys.executable, os.path.join(RECIPES, "ir9_outcopy.py"), "work/ott_m10.ll", "work/ott_m10.ll", "--report", "work/outcopy.json"],
           W, log, "outcopy")
    final = open(os.path.join(W, "work/ott_m10.ll")).read()
    res["O4_m10_ll_identical"] = same(final, os.path.join(M10, "work", "ott_m10.ll")) if not auto and legacy else None
    # ---- O5 data image (va_base=LB_BASE, CAB-220)
    dc, cnt = dataimage.gen_data_c(img, va_base=LB)
    open(os.path.join(W, "work/ott_data.c"), "w").write(dc)
    res["O5_data_c_reloc_fixes"] = cnt
    # ---- O6 SIMD helper 自動生成 (正規名)
    canon, mp = SG.canonicalize(final)
    open(os.path.join(W, "work/ott_m10_canon.ll"), "w").write(canon)
    decls = SG.scan_decls(canon)
    c, rep = SG.emit_c(decls, use_names="canon")
    open(os.path.join(W, "work/ott_simd.c"), "w").write(c)
    res["simd"] = dict(helpers=len(rep["generated"]), unsupported=[u[0] for u in rep["unsupported"]], approx=rep["approx"])
    if not build:
        return res, log
    # ---- O7 emcc (m10_build.sh と同一フラグ。lowbase は lb_layout の値 + -DLB_* / -sINITIAL_MEMORY)
    exports = re.search(r"-sEXPORTED_FUNCTIONS=(\S+)", open(os.path.join(M6, "m6_build.sh")).read()).group(1)
    rt, rt_rep = runtime_lb.emit(
        {"m6_rt.c": os.path.join(M6, "m6_rt.c"), "m8_rt.c": os.path.join(M8, "m8_rt.c"),
         "m10_boot.c": os.path.join(M10, "m10_boot.c"),
         "m6_stubs_hand.c": os.path.join(M6, "work", "m6_stubs_hand.c"),
         "m6_stubs_hand2.c": os.path.join(M6, "work", "m6_stubs_hand2.c")},
        os.path.join(W, "work", "rt_lb"))
    res["runtime_lb"] = runtime_lb.audit_summary(rt_rep)
    srcs = [os.path.join(W, "work/ott_data.c"), os.path.join(M6, "work/m6_stubs.c"),
            os.path.join(TOOLS, "shim/src/heap.c"), os.path.join(TOOLS, "shim/src/failfast.c"), rt["m6_rt.c"],
            rt["m6_stubs_hand.c"], rt["m6_stubs_hand2.c"],
            rt["m8_rt.c"], os.path.join(M9, "m9_rt.c"), rt["m10_boot.c"]]
    if helpers == "gen":
        srcs = [os.path.join(W, "work/ott_simd.c")] + srcs
        ll = os.path.join(W, "work/ott_m10_canon.ll")
        inc = ["-I", SIMD_DIR, "-ffp-contract=off", "-frounding-math", "-fno-fast-math"]
        out = os.path.join(W, "ott_gen.cjs")
    else:                                      # m6 手製 helper (比較用)
        srcs = [os.path.join(M6, "msimd6.c")] + srcs
        ll = os.path.join(W, "work/ott_m10.ll")
        inc = []
        out = os.path.join(W, "ott_m6helpers.cjs")
    cmd = ["emcc"] + srcs + [ll, "-sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64", "-o", out + ".tmp", "-w",
                             "-Wno-error=int-conversion", "-Wno-implicit-function-declaration", "-O0", "-g1", "-sALLOW_MEMORY_GROWTH=1",
                             "-sSTACK_SIZE=8MB", "-sGLOBAL_BASE=%d" % L["LB_GLOBAL_BASE"], "-sENVIRONMENT=node", "-sMODULARIZE=1",
                             "-sEXPORT_NAME=createModule", "-sERROR_ON_UNDEFINED_SYMBOLS=0", "-sEXIT_RUNTIME=1",
                             "-sEXPORTED_FUNCTIONS=" + exports, "-Wl,--no-gc-sections"] + inc
    if legacy:
        # 元 m10 build と同一 (-Wl,--initial-memory は emscripten initial-heap が加算されても
        # GLOBAL_BASE=256MiB の hole が十分あるため成立する)
        cmd += ["-Wl,--initial-memory=%d" % L["LB_INIT"], "-Wl,--max-memory=%d" % L["LB_MAX"]]
    else:
        # lowbase: -Wl,--initial-memory だと initial-heap 既定 16MiB が加算され "initial memory too small"
        # になるため -sINITIAL_MEMORY/-sMAXIMUM_MEMORY を使う (lowbase integration.md §A / build_m10_lb.sh 同規約)
        cmd += ["-sINITIAL_MEMORY=%d" % L["LB_INIT"], "-sMAXIMUM_MEMORY=%d" % L["LB_MAX"]] + runtime_lb.emcc_defs(LB, L["LB_MAX"])
    t0 = time.time()
    r = env.run(cmd, capture_output=True, text=True, cwd=W)
    log.append("emcc: rc=%d %.1fs" % (r.returncode, time.time() - t0))
    if r.returncode:
        raise RuntimeError("emcc failed:\n" + r.stderr[-3000:])
    open(os.path.join(W, "build.log"), "w").write(r.stderr)
    und = set(re.findall(r"undefined symbol: ([\w.]+)", r.stderr))
    res["link_warnings"] = dict(signature_mismatch=len(re.findall(r"signature mismatch", r.stderr)),
                                undefined=len(und), undefined_asm=len([x for x in und if x.startswith("__asm_")]))
    os.replace(out + ".tmp", out)
    for ext in (".wasm",):
        if os.path.exists(out + ".tmp" + ext):
            os.replace(out + ".tmp" + ext, out + ext)
    res["cjs"] = out
    # e2e ハーネス (recipes/ott/*.mjs) へのレイアウト指示 (既定 = legacy の値なので低 base 時のみ必要)
    if not legacy:
        res["e2e_env"] = {"LB_BASE": "%d" % LB, "LB_ARENA": "%d" % L["LB_ARENA"]}
    return res, log


def e2e_checks(cjs, workdir, label="", env_extra=None, outhash=True):
    """m10_e2e.sh の E1..E7 を再現して判定する。env_extra: lowbase 時の {LB_BASE, LB_ARENA}。

    lowbase 時は出力 SHA 突合 (ott_outhash) の合格基準を [0x248]=0 組 (f0) にする:
    [0x248]=1 経路は未初期化読み (junk) が stack/heap 絶対位置に依存し, base/heap 移動で
    junk-tiny が変わり得るため (lowbase REPORT §4.3 実測: 128,000 cell 中 2 cell)。
    outhash=False (CAB-238: auto 既定モード) は SHA 突合を省略する — auto f7,p1 は修復由来で
    m10 参照と SHA が一致しないのが正であり, 差分表は REPORT_APPENDIX_A.md §12 を参照。
    """
    W = os.path.abspath(workdir)
    env.ensure()
    e = dict(os.environ, OTT_CJS=os.path.abspath(cjs))
    if env_extra:
        e.update(env_extra)
    out = {}
    r = subprocess.run(["node", os.path.join(RECIPES, "e2e_check.mjs")], capture_output=True, text=True, env=e, timeout=600)
    txt = r.stdout + r.stderr
    m = re.search(r"checks (\d+) / broken (\d+)", txt)
    out["checks"], out["broken"] = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    out["e2e_rc"] = r.returncode
    m0 = re.search(r"census \[0x248\]=0 : (\{.*\})", txt)
    m1 = re.search(r"census \[0x248\]=1 : (\{.*\})", txt)
    out["census0"] = m0.group(1) if m0 else None
    out["census1"] = m1.group(1) if m1 else None
    out["log"] = txt
    r = subprocess.run(["node", os.path.join(RECIPES, "m10_coefdump.mjs")], capture_output=True, text=True, env=e, timeout=300)
    dump = os.path.join(W, "coefdump%s.json" % label)
    open(dump, "w").write(r.stdout)
    r2 = subprocess.run([sys.executable, os.path.join(RECIPES, "m10_coefref.py"), dump], capture_output=True, text=True)
    try:
        j = json.loads(r2.stdout.strip().splitlines()[-1])
        out["maxdev"], out["nbad"] = j["maxdev"], j["nbad"]
    except Exception:
        out["maxdev"], out["nbad"] = None, None
    r = subprocess.run(["node", os.path.join(RECIPES, "e2e_trap10.mjs")], capture_output=True, text=True, env=e, timeout=300)
    out["trap_rc"] = r.returncode
    out["trap_log"] = r.stdout
    out["pass"] = (out["broken"] == 0 and out["e2e_rc"] == 0 and out["maxdev"] == 0.0 and out["nbad"] == 0 and out["trap_rc"] == 0)
    ref = os.path.join(M10, "work", "ott_m10.cjs")
    out["outhash"] = None
    if outhash and os.path.exists(ref) and os.path.abspath(cjs) != os.path.abspath(ref):
        try:
            hs = []
            # 比較対象 (元 m10 成果物) は legacy base の module → 既定 env (env_extra 無し) で駆動する
            for c, ee in ((cjs, env_extra), (ref, None)):
                e2 = dict(os.environ, OTT_CJS=os.path.abspath(c))
                if ee:
                    e2.update(ee)
                # 42 combo × module 初期化 (864MiB) を 2 module 分: 実測 約 7 分/module (CAB-238) ゆえ 1800 秒
                r = subprocess.run(["node", os.path.join(RECIPES, "ott_outhash.mjs")], capture_output=True, text=True, env=e2, timeout=1800)
                hs.append(json.loads(r.stdout))
            f0 = [k for k in hs[0] if "_f0_" in k]
            out["outhash"] = dict(combos=len(hs[0]), equal=hs[0] == hs[1], distinct=len(set(hs[0].values())),
                                  f0_equal=sum(1 for k in f0 if hs[0][k] == hs[1][k]), f0_total=len(f0))
            if env_extra:                     # lowbase: [0x248]=0 組の bit 一致を合格基準にする
                out["pass"] = out["pass"] and out["outhash"]["f0_equal"] == out["outhash"]["f0_total"]
            else:
                out["pass"] = out["pass"] and out["outhash"]["equal"]
        except Exception as ex:                  # noqa
            out["outhash"] = dict(error=str(ex)[:200])
    return out
