#!/usr/bin/env python3
"""tests/test_stdbuild.py — 標準ビルド設定 + 署名ガード (PERF-P1 / #155) のテスト。plugin バイナリ・RetDec 不要。

  U1-U6  設定/フラグ/禁止フラグ/guard 判定/正規化署名 (emcc 不要)
  S1     合成 lift IR (tests/std/synth.ll) を pipeline.build_variants で ref/o2/o3/std 全変種ビルド → 署名一致 + <name>.cjs 確定
  S2     ネガティブコントロール: 同 IR に -ffast-math の変種 (variant_extra) を足すと署名ガードが FAIL・<name>.cjs を作らない
  S3     enforce profile (std) に -msimd128 を足すと StdBuildError / --expect 不一致で SignatureMismatch / 失敗時 <name>.cjs 無し
  C1     x64c 形の C ビルド (emcc_cmd + 外部 probe): CLI `stdbuild.py guard` が全変種一致で exit 0、-ffast-math 変種を足すと exit 1。
         basename が同じ別ファイル (a/x.cjs b/x.cjs) は 1 件に潰れず 2 変種として比較される
  N1-N4  fail-open の封じ込め (ネガティブコントロール; 全変種が「同じ失敗」をしても PASS にしない):
         N1 番兵署名 (TIMEOUT / PROBE-FAIL / 空) 同士の guard が SignatureMismatch   N2 存在しない probe / 空 cjs / 重複 / 1 件の CLI guard が exit 1
         N3 canon_digest が R 行 0 件で StdBuildError                              N4 build_variants が全変種 TIMEOUT / R 行 0 件で SignatureMismatch・<name>.cjs 無し
前提: emcc (EMSDK_DIR) / node / python capstone,pefile (pipeline の import 用)。使い方: python3 tests/test_stdbuild.py [WORKDIR]
WORKDIR は存在しない dir のみ受け付ける (既存 dir は消さず拒否)。省略時の work/stdbuild_test (gitignore 配下の専用 scratch) だけは毎回作り直す。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, PKG)
EXPLICIT_WORK = len(sys.argv) > 1
WORK = os.path.abspath(sys.argv[1]) if EXPLICIT_WORK else os.path.join(PKG, "work", "stdbuild_test")
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
    if not EXPLICIT_WORK:
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

def n1():
    for pair in ({"a": "TIMEOUT", "b": "TIMEOUT"}, {"a": "PROBE-FAIL(rc=1)", "b": "PROBE-FAIL(rc=1)"}, {"a": "", "b": ""},
                 {"a": "NO-RESULT", "b": "NO-RESULT"}, {"a": "TIMEOUT"}):
        for exp in (None, "TIMEOUT"):
            try:
                SB.guard(pair, exp)
                raise SystemExit("N1: 番兵署名 %r が guard を通った (fail-open)" % (pair,))
            except SB.SignatureMismatch:
                pass
    assert SB.guard({"a": "ddd24d66", "b": "ddd24d66"})["ok"]    # 通常署名は従来どおり通る
    print("N1 ok (番兵 TIMEOUT / PROBE-FAIL / NO-RESULT / 空 は全変種同値でも SignatureMismatch)")


def n2():
    probe = os.path.join(HERE, "std", "synth_probe.mjs")
    g = [sys.executable, os.path.join(PKG, "liftlib", "stdbuild.py"), "guard", "--regex", r'"sig":"(\w+)"']
    with tempfile.TemporaryDirectory() as td:
        for d in ("a", "b"):
            os.makedirs(os.path.join(td, d))
            open(os.path.join(td, d, "x.cjs"), "w").close()
        a, b = os.path.join(td, "a", "x.cjs"), os.path.join(td, "b", "x.cjs")
        cases = (("存在しない probe", ["--probe", "node /nonexistent_probe.mjs {cjs}", a, b]),
                 ("空 cjs", ["--probe", "node %s {cjs}" % probe, a, b]),
                 ("存在しない cjs", ["--probe", "node %s {cjs}" % probe, os.path.join(td, "no1.cjs"), os.path.join(td, "no2.cjs")]),
                 ("重複パス", ["--probe", "node %s {cjs}" % probe, a, a]),
                 ("1 件のみ", ["--probe", "node %s {cjs}" % probe, a]))
        for name, args in cases:
            r = subprocess.run(g + args, capture_output=True, text=True)
            assert r.returncode == 1, "N2: %s で CLI guard が exit 1 にならない (rc=%d): %s" % (name, r.returncode, r.stdout + r.stderr)
    print("N2 ok (CLI guard: 存在しない probe / 空 cjs / 存在しない cjs / 重複 / 1 件のみ はいずれも exit 1)")


def n3():
    for txt in ("", "S 0\nE 0", "D out 00112233 -\n"):
        try:
            SB.canon_digest(txt, {})
            raise SystemExit("N3: R 行 0 件の出力 %r を署名化できてしまう (fail-open)" % txt)
        except SB.StdBuildError:
            pass
    print("N3 ok (canon_digest: R 行 0 件は StdBuildError)")


def n4():
    from liftlib import pipeline, ir as IR
    from liftlib.harness import diff as D
    cfg = pipeline.load_cfg(os.path.join(HERE, "std", "synth_target.json"))
    real_run = D.run_wasm

    def timeout_run(cjs, fn, sigp, scen, outp, timeout=240):
        open(outp, "w").close()
        return None

    def empty_run(cjs, fn, sigp, scen, outp, timeout=240):
        open(outp, "w").write("S 0\nE 0\n")
        return True

    base = tempfile.mkdtemp(prefix="n4_")
    try:
        for name, fake, want in (("全変種 TIMEOUT", timeout_run, "TIMEOUT"), ("全変種 R 行 0 件", empty_run, "NO-RESULT")):
            wd = os.path.join(base, want)
            os.makedirs(wd)
            D.run_wasm = fake
            try:
                pipeline.build_variants(cfg, IR.Module.parse(open(os.path.join(HERE, "std", "synth.ll")).read()), wd, [], {}, variants=["ref"])
                raise SystemExit("N4: %s で build_variants が成功した (fail-open)" % name)
            except SB.SignatureMismatch as e:
                assert want in str(e), str(e)
            finally:
                D.run_wasm = real_run
            assert not os.path.exists(os.path.join(wd, cfg["name"] + ".cjs")), "N4: %s なのに <name>.cjs ができている" % name
            sj = json.load(open(os.path.join(wd, cfg["name"] + ".sig.json")))
            assert {v["sig"] for v in sj["variants"].values()} == {want}
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("N4 ok (build_variants: 全変種 TIMEOUT / R 行 0 件でも SignatureMismatch・成果物 <name>.cjs 無し)")


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
    for d in ("da", "db"):
        os.makedirs(os.path.join(wd, d))
        shutil.copyfile(outs["std"][:-4] + ".wasm", os.path.join(wd, d, "std.wasm"))    # cjs は自身の wasm 名 (std.wasm) を参照する
        shutil.copyfile(outs["std"], os.path.join(wd, d, "x.cjs"))
    same = subprocess.run(g + [os.path.join(wd, "da", "x.cjs"), os.path.join(wd, "db", "x.cjs")], capture_output=True, text=True)
    assert same.returncode == 0 and "2 変種" in same.stdout, "同名 basename の別ファイルが 1 件に潰れている: " + same.stdout + same.stderr
    print("C1 ok (CLI guard: 3 変種一致 exit 0 / -ffast-math 変種を足すと exit 1 / --expect 不一致 exit 1 / 同名 basename 2 件を 2 変種として比較)")
    print("   " + bad.stdout.strip().splitlines()[-1] if bad.stdout.strip() else "")


if __name__ == "__main__":
    if EXPLICIT_WORK and os.path.exists(WORK):
        sys.exit("[test_stdbuild] WORKDIR %s は既に存在する。消さずに拒否する (存在しない dir を指定するか省略)" % WORK)
    u1_u6()
    n1()
    n2()
    n3()
    s1_s3()
    n4()
    c1()
    print("test_stdbuild: ALL PASS")
