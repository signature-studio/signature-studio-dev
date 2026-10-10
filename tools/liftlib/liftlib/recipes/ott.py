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

from .. import env, ir as IR
from ..pe import Image
from ..passes import base as B, p1_legacy, remap, dataimage
from ..simd import gen as SG

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
TOOLS = os.path.join(ROOT, "tools")
M6, M8, M9, M10 = (os.path.join(TOOLS, x) for x in ("m6", "m8", "m9", "m10"))
RECIPES = os.path.join(HERE, "ott")
DLL = "/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll"
SIMD_DIR = os.path.join(HERE, "..", "simd")


def nb(text):
    return [l for l in text.split("\n") if l.strip()]


def same(text, ref_path):
    if not os.path.exists(ref_path):
        return None
    return nb(text) == nb(open(ref_path).read())


def sh(cmd, cwd, log, name):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    log.append("%s: rc=%d %.1fs" % (name, r.returncode, time.time() - t0))
    if r.returncode:
        raise RuntimeError("%s failed:\n%s\n%s" % (name, r.stdout[-1500:], r.stderr[-1500:]))
    return r


def run(workdir, build=True, helpers="gen", auto=()):
    W = os.path.abspath(workdir)
    os.makedirs(os.path.join(W, "work"), exist_ok=True)
    log, res = [], {}
    img = Image(DLL)
    for f in ("full_t1.drc.ll", "full_t1.drc.dsm"):
        dst = os.path.join(W, "work", f)
        if not os.path.exists(dst):
            os.symlink(os.path.join(M6, "work", f), dst)
    # ---- O1 base 正規化
    t0 = time.time()
    raw = open(os.path.join(M6, "work", "ott.drc.ll")).read()
    text, brep = B.run_base(raw, B.make_args())
    mod0 = IR.Module.parse(text)
    if auto:
        from ..passes import f7 as F7, p1 as P1
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
    res["O1_base_identical_to_m6_ott_lift"] = same(lift, os.path.join(M6, "work", "ott_lift.ll")) if not auto else None
    log.append("O1 base: %.1fs b1=%s a9res=%s" % (time.time() - t0, brep.get("b1_fixed"), brep.get("a9_residual_constexpr")))
    # ---- O2 P1(legacy 配線) → VA shift → gdata
    p1t, st = p1_legacy.legacy_p1(lift)
    res["O2a_p1_identical"] = same(p1t, os.path.join(M6, "work", "ir7e_p1.ll"))
    res["p1_stats"] = st
    sht, nnum = remap.shift_va(p1t)
    res["O2b_shift_identical"] = same(sht, os.path.join(M6, "work", "ir7e_p2.ll"))
    gdt, gst = remap.gdata_legacy(sht, img)
    open(os.path.join(W, "ott_shift3b.ll"), "w").write(gdt)
    res["O2c_gdata_identical"] = same(gdt, os.path.join(M6, "work", "ir7e_p3.ll"))
    res["gdata"] = gst
    # ---- O3 memfix / full_extract (vendored recipes)
    sh([sys.executable, os.path.join(RECIPES, "m6_memfix.py"), "ott_shift3b.ll", "work/ott_memfix0.ll"], W, log, "memfix")
    res["O3a_memfix0_identical"] = same(open(os.path.join(W, "work/ott_memfix0.ll")).read(), os.path.join(M6, "work", "ott_memfix0.ll"))
    sh([sys.executable, os.path.join(RECIPES, "m6_full_extract.py"), "work/ott_memfix1.ll",
        "function_1801260c0", "function_180126030", "function_180126010"], W, log, "full_extract")
    res["O3b_memfix1_identical"] = same(open(os.path.join(W, "work/ott_memfix1.ll")).read(), os.path.join(M6, "work", "ott_memfix1.ll"))
    # ---- O4 m8/m9 recipes
    sh([sys.executable, os.path.join(RECIPES, "ir7_argpass_fixed.py"), "work/ott_memfix1.ll", "work/ott_argpass8.ll",
        "--dsm", "work/full_t1.drc.dsm", "--report", "work/argpass8.json", "--target", "function_180120af0",
        "--tail", "function_18011de50"], W, log, "argpass")
    sh([sys.executable, os.path.join(RECIPES, "ir8_valueflow.py"), "work/ott_argpass8.ll", "work/ott_m8.ll", "--dsm", "work/full_t1.drc.dsm",
        "--full-ir", "work/full_t1.drc.ll", "--report", "work/valueflow.json", "--targets", "function_180126030"], W, log, "valueflow")
    sh([sys.executable, os.path.join(RECIPES, "ir9_bootstraps.py"), "work/ott_m8.ll", "work/ott_m10.ll", "--dsm", "work/full_t1.drc.dsm",
        "--report", "work/bootstraps.json"], W, log, "bootstraps")
    if "f7" not in auto:        # 汎用 F7 (passes/f7.py) が outcopy を包含するため, auto=f7 のときは省略
        sh([sys.executable, os.path.join(RECIPES, "ir9_outcopy.py"), "work/ott_m10.ll", "work/ott_m10.ll", "--report", "work/outcopy.json"],
           W, log, "outcopy")
    final = open(os.path.join(W, "work/ott_m10.ll")).read()
    res["O4_m10_ll_identical"] = same(final, os.path.join(M10, "work", "ott_m10.ll")) if not auto else None
    # ---- O5 data image
    dc, cnt = dataimage.gen_data_c(img)
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
    # ---- O7 emcc (m10_build.sh と同一フラグ)
    exports = re.search(r"-sEXPORTED_FUNCTIONS=(\S+)", open(os.path.join(M6, "m6_build.sh")).read()).group(1)
    srcs = [os.path.join(W, "work/ott_data.c"), os.path.join(M6, "work/m6_stubs.c"),
            os.path.join(TOOLS, "shim/src/heap.c"), os.path.join(TOOLS, "shim/src/failfast.c"), os.path.join(M6, "m6_rt.c"),
            os.path.join(M6, "work/m6_stubs_hand.c"), os.path.join(M6, "work/m6_stubs_hand2.c"),
            os.path.join(M8, "m8_rt.c"), os.path.join(M9, "m9_rt.c"), os.path.join(M10, "m10_boot.c")]
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
                             "-sSTACK_SIZE=8MB", "-sGLOBAL_BASE=268435456", "-sENVIRONMENT=node", "-sMODULARIZE=1",
                             "-sEXPORT_NAME=createModule", "-sERROR_ON_UNDEFINED_SYMBOLS=0", "-sEXIT_RUNTIME=1",
                             "-sEXPORTED_FUNCTIONS=" + exports, "-Wl,--no-gc-sections",
                             "-Wl,--initial-memory=%d" % 0x36000000, "-Wl,--max-memory=%d" % 0x36000000] + inc
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
    return res, log


def e2e_checks(cjs, workdir, label=""):
    """m10_e2e.sh の E1..E7 を再現して判定する。"""
    W = os.path.abspath(workdir)
    env.ensure()
    e = dict(os.environ, OTT_CJS=os.path.abspath(cjs))
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
    if os.path.exists(ref) and os.path.abspath(cjs) != os.path.abspath(ref):
        try:
            hs = []
            for c in (cjs, ref):
                e2 = dict(os.environ, OTT_CJS=os.path.abspath(c))
                r = subprocess.run(["node", os.path.join(RECIPES, "ott_outhash.mjs")], capture_output=True, text=True, env=e2, timeout=900)
                hs.append(json.loads(r.stdout))
            out["outhash"] = dict(combos=len(hs[0]), equal=hs[0] == hs[1], distinct=len(set(hs[0].values())))
        except Exception as ex:                  # noqa
            out["outhash"] = dict(error=str(ex)[:200])
    return out
