#!/usr/bin/env python3
"""tests/test_stdbuild.py — 標準ビルド設定 + 署名ガード (PERF-P1 / #155) のテスト。plugin バイナリ・RetDec 不要。

  U1-U6  設定/フラグ/禁止フラグ/guard 判定/正規化署名 (emcc 不要)
  S1     合成 lift IR (tests/std/synth.ll) を pipeline.build_variants で ref/o2/o3/std 全変種ビルド → 署名一致 + <name>.cjs 確定
  S2     ネガティブコントロール: 同 IR に -ffast-math の変種 (variant_extra) を足すと署名ガードが FAIL・<name>.cjs を作らない
  S3     enforce profile (std) に -msimd128 を足すと StdBuildError / --expect 不一致で SignatureMismatch / 失敗時 <name>.cjs 無し
  C1     x64c 形の C ビルド (emcc_cmd + 外部 probe): CLI `stdbuild.py guard` が全変種一致で exit 0、-ffast-math 変種を足すと exit 1
前提: emcc (EMSDK_DIR) / node / python capstone,pefile (pipeline の import 用)。使い方: python3 tests/test_stdbuild.py [WORKDIR]
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, PKG)
WORK = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(PKG, "work", "stdbuild_test")
from liftlib import stdbuild as SB   # noqa: E402


def u1_u6():
    c = SB.load()
    assert c["default_profile"] == "std" and c["guard_variants"] == ["ref", "o2", "o3", "std"]
    # U1 std = -O3 -flto + gc-sections。-msimd128 / wasm-opt 追加段 / -ffast-math は含まない
    f = SB.flags("std")
    assert f[:2] == ["-O3", "-flto"] and "-Wl,--gc-sections" in f and "-msimd128" not in f and "-ffast-math" not in f, f
    # U2 dev は旧 pipeline.build の emcc 先頭引数列と完全一致 (後方互換)
    assert SB.flags("dev", rounding_math=True) == ["-O1", "-ffp-contract=off", "-frounding-math", "-fno-fast-math", "-Wl,--no-gc-sections"]
    # U3 ref = -O0 / no-gc (署名の基準)
    assert SB.flags("ref")[0] == "-O0" and "-Wl,--no-gc-sections" in SB.flags("ref")
    # U4 禁止フラグ: enforce profile だけ検査。自身の opt/link は違反にならない
    assert SB.violations("std", SB.flags("std") + ["-msimd128", "-ffast-math"]) == ["-msimd128", "-ffast-math"]
    assert SB.violations("ref", ["-O0", "-msimd128"]) == [] and SB.violations("std", SB.flags("std")) == []
    try:
        SB.emcc_cmd("std", ["a.c"], "o.js", exports=["f"], cflags_extra=["-O1"])
        raise SystemExit("U4: -O1 混入を検出できていない")
    except SB.StdBuildError:
        pass
    assert "-sEXPORTED_FUNCTIONS=_f,_g" in SB.emcc_cmd("std", ["a.c"], "o.js", exports=["f", "_g"])
    # U5 guard
    assert SB.guard({"a": "x", "b": "x"}, "x")["ok"]
    for bad, exp in (({"a": "x", "b": "y"}, None), ({"a": "x", "b": "x"}, "z")):
        try:
            SB.guard(bad, exp)
            raise SystemExit("U5: 不一致を検出できていない")
        except SB.SignatureMismatch:
            pass
    # U6 正規化署名: 生ポインタ rax / ignore_buffers は署名に入れない。バッファ 1 byte 違いは署名が変わる
    base = "S 0\nR 0 0 0 0000000000001234 0000000000000000\nD out 00112233 -\nD junk aa -\nE 0"
    spec = {"ignore_buffers": ["junk"]}
    d0 = SB.canon_digest(base, spec)
    assert SB.canon_digest(base.replace("1234", "9999").replace("D junk aa", "D junk bb"), spec) == d0
    assert SB.canon_digest(base.replace("00112233", "00112234"), spec) != d0
    assert SB.canon_digest(base.replace("1234", "9999"), dict(spec, compare_ret=True)) != SB.canon_digest(base, dict(spec, compare_ret=True))
    print("U1-U6 ok (設定・フラグ・禁止フラグ・guard・正規化署名)")


def s1_s3():
    from liftlib import pipeline, ir as IR
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    cfg = pipeline.load_cfg(os.path.join(HERE, "std", "synth_target.json"))
    mod = IR.Module.parse(open(os.path.join(HERE, "std", "synth.ll")).read())
    log, stats = [], {}
    t0 = time.time()
    cjs, rep = pipeline.build_variants(cfg, mod, WORK, log, stats)
    print("S1 ok: %s (%.1fs, 署名 %s)" % (os.path.basename(cjs), time.time() - t0, rep["guard"]["unique"][0]))
    for v, r in rep["variants"].items():
        print("   %-4s wasm %6d B  build %5.2fs  run %4.2fs  sig %s" % (v, r["wasm_bytes"], r["build_s"], r["run_s"], r["sig"]))
    assert os.path.exists(cjs) and sorted(rep["variants"]) == ["o2", "o3", "ref", "std"] and len(rep["guard"]["unique"]) == 1
    assert json.load(open(os.path.join(WORK, "synth.sig.json")))["guard"]["ok"]
    # S2 ネガティブコントロール: -ffast-math 変種 (x/3.0 → x*(1/3.0) の reciprocal 化) を足す
    cfg2 = dict(cfg, name="synth_neg", emcc=dict(cfg["emcc"], variant_extra={"fastmath": ["-ffast-math"]}))
    wd2 = os.path.join(WORK, "neg")
    os.makedirs(wd2)
    mod2 = IR.Module.parse(open(os.path.join(HERE, "std", "synth.ll")).read())
    try:
        pipeline.build_variants(cfg2, mod2, wd2, [], {}, variants=["ref", "fastmath=dev"], profile="ref")
        raise SystemExit("S2: -ffast-math 変種で署名ガードが FAIL しなかった")
    except SB.SignatureMismatch as e:
        print("S2 ok (ネガティブコントロール: -ffast-math で FAIL): %s" % str(e)[:140])
    assert not os.path.exists(os.path.join(wd2, "synth_neg.cjs")), "失敗時に成果物を作ってはいけない"
    # S3 enforce / expect
    try:
        pipeline.emit(dict(cfg, emcc=dict(cfg["emcc"], extra=["-msimd128"])), pipeline.prepare(cfg, mod, WORK, {}), WORK, "std", tag="simd")
        raise SystemExit("S3: std への -msimd128 混入を検出できていない")
    except SB.StdBuildError:
        pass
    wd3 = os.path.join(WORK, "exp")
    os.makedirs(wd3)
    try:
        pipeline.build_variants(cfg, IR.Module.parse(open(os.path.join(HERE, "std", "synth.ll")).read()), wd3, [], {}, variants=["ref"], expect="deadbeefdeadbeef")
        raise SystemExit("S3: 期待署名不一致を検出できていない")
    except SB.SignatureMismatch as e:
        assert not os.path.exists(os.path.join(wd3, "synth.cjs"))
        print("S3 ok (-msimd128 混入 / 期待署名 deadbeef… 不一致でいずれも FAIL・成果物なし)")


def c1():
    wd = os.path.join(WORK, "c")
    os.makedirs(wd)
    srcs = [os.path.join(HERE, "std", "synth_x64c.c"), os.path.join(HERE, "std", "synth_helper.c")]
    link = ["-w", "-sALLOW_MEMORY_GROWTH=1", "-sSTACK_SIZE=2MB", "-sGLOBAL_BASE=268435456", "-sENVIRONMENT=node", "-sMODULARIZE=1",
            "-sEXPORT_NAME=createModule", "-sEXIT_RUNTIME=1", "-sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32",
            "-Wl,--initial-memory=%d" % 0x12000000, "-Wl,--max-memory=%d" % 0x12000000]
    outs = {}
    for tag, prof, extra in (("ref", "ref", []), ("o2", "o2", []), ("std", "std", []), ("fastmath", "dev", ["-ffast-math"])):
        out = os.path.join(wd, tag + ".cjs")
        cmd = SB.emcc_cmd(prof, srcs, out, exports=["synth_run", "malloc"], link_extra=link, cflags_extra=extra)
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1500:]
        outs[tag] = out
        print("   c1 %-8s wasm %6d B  build %5.2fs" % (tag, os.path.getsize(out[:-4] + ".wasm"), time.time() - t0))
    g = [sys.executable, os.path.join(PKG, "liftlib", "stdbuild.py"), "guard", "--probe", "node %s {cjs}" % os.path.join(HERE, "std", "synth_probe.mjs"),
         "--regex", r'"sig":"(\w+)"']
    ok = subprocess.run(g + [outs["ref"], outs["o2"], outs["std"]], capture_output=True, text=True)
    print(ok.stdout.rstrip())
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = subprocess.run(g + [outs["ref"], outs["o2"], outs["std"], outs["fastmath"]], capture_output=True, text=True)
    assert bad.returncode == 1, "fastmath 変種で exit 1 にならない: " + bad.stdout
    bad2 = subprocess.run(g + ["--expect", "deadbeef", outs["ref"], outs["std"]], capture_output=True, text=True)
    assert bad2.returncode == 1
    print("C1 ok (CLI guard: 3 変種一致 exit 0 / -ffast-math 変種を足すと exit 1 / --expect 不一致 exit 1)")
    print("   " + bad.stdout.strip().splitlines()[-1] if bad.stdout.strip() else "")


if __name__ == "__main__":
    u1_u6()
    s1_s3()
    c1()
    print("test_stdbuild: ALL PASS")
