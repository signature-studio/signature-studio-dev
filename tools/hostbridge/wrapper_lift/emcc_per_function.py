"""生成 C を emcc -c で通し、関数単位の通過数を集計する (#1128 受入条件 1・2)。

使い方 (cwd=リポジトリルート):
  EM_CONFIG=<emsdk>/.emscripten PATH=<emsdk>/upstream/emscripten:$PATH \
    python3 tools/hostbridge/wrapper_lift/emcc_per_function.py <dir_or_file_c> [...] --targets <block.bin> --out <json>
入力: 1 ファイル = 1 emcc -c 呼び出し。ディレクトリ指定時は中の *.c を全部対象にする。
判定: error 行 (`file:line:col: error:` / `fatal error:`) を、その行を含む関数定義 `function_<hex>(...) {` に帰属させる。
  通過 = 定義を持ち、本体内に error が無い関数。
fail-closed: emcc が非 0 終了 (timeout 含む) で、かつ全 error が関数に帰属できない場合
  (error 0 件・関数外 (global)・別ファイル・書式外の error 行 `unattributed`) は、そのファイルの全 defined 関数を失敗にする。
出力: 関数数・通過数・error 行数・global error 数・unattributed error 数・fail-closed で落としたファイル数・
  所要秒・emcc 呼び出しの exit 内訳 (`timeout` を含む) を JSON で書く。
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
import time

DEF_RE = re.compile(r"^[^\s/][^\n;=]*\bfunction_([0-9a-f]+)\s*\([^\n;{}]*\)\s*\{", re.M)
ERR_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\d+: (?:fatal )?error: ", re.M)
ANY_ERR_RE = re.compile(r"(?:^|\n)[^\n]*\berror: ", re.M)


def run_one(path, tmp_o, timeout, extra, cc):
    t0 = time.time()
    try:
        p = subprocess.run(
            [cc, "-c", "-w", "-O0", "-fno-strict-aliasing", "-ferror-limit=0"] + extra + [path, "-o", tmp_o],
            capture_output=True, text=True, timeout=timeout,
        )
        rc, out = p.returncode, p.stderr + p.stdout
    except subprocess.TimeoutExpired:
        rc, out = "timeout", ""
    return rc, out, time.time() - t0


def attribute(text, out, errs_out, fname):
    defs = [(text.count("\n", 0, m.start()) + 1, int(m.group(1), 16)) for m in DEF_RE.finditer(text)]
    starts = [ln for ln, _ in defs]
    bad = set()
    attributed = 0
    for m in ERR_RE.finditer(out):
        if os.path.basename(m.group("file")) != os.path.basename(fname):
            continue
        line = int(m.group("line"))
        errs_out["errors"] += 1
        attributed += 1
        i = _bisect_right(starts, line) - 1
        if i < 0:
            errs_out["global"] += 1
        else:
            bad.add(defs[i][1])
    errs_out["unattributed"] += max(0, len(ANY_ERR_RE.findall(out)) - attributed)
    return bad


def _bisect_right(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--targets", required=True, help="PE (block*.bin) のパス。pdata 関数集合を対象にする")
    ap.add_argument("--cflags", default="", help="追加 emcc フラグ (空白区切り)。既定は修復なし")
    ap.add_argument("--cc", default="emcc", help="コンパイラ (既定 emcc)。ネガティブコントロール用に差し替える")
    ap.add_argument("--force-fail-file", action="append", default=[], help="このファイルを timeout 扱いにする (fail-closed の検証用)")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "liftlib"))
    from liftlib.pe import Image
    img = Image(a.targets)
    targets, seen = set(), set()
    for (b, _e) in img.pdata_functions():
        r = img.func_at(b, merge=True)
        if r and r not in seen:
            seen.add(r)
            targets.add(r[0])
    files = []
    for x in a.inputs:
        if os.path.isdir(x):
            files += sorted(os.path.join(x, f) for f in os.listdir(x) if f.endswith(".c"))
        else:
            files.append(x)
    defined, bad_all = set(), set()
    errs = collections.Counter()
    rcs = collections.Counter()
    failclosed_files = 0
    seconds = 0.0
    t_all = time.time()
    tmpd = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    for f in files:
        with open(f, errors="replace") as fh:
            text = fh.read()
        fdefs = {int(m.group(1), 16) for m in DEF_RE.finditer(text)}
        defined |= fdefs
        if f in a.force_fail_file:
            rc, out, dt = "timeout", "", 0.0
        else:
            rc, out, dt = run_one(f, os.path.join(tmpd, "o.o"), a.timeout, a.cflags.split(), a.cc)
        seconds += dt
        rcs[str(rc)] += 1
        if rc != 0:
            unattr_before = errs["unattributed"]
            file_bad = attribute(text, out, errs, f)
            bad_all |= file_bad
            # fail-closed: 非 0 終了で、関数へ帰属した失敗が無い or 帰属できない error 行がある場合は、ファイル全体を失敗にする
            if not file_bad or errs["unattributed"] > unattr_before:
                bad_all |= fdefs
                failclosed_files += 1
    defined &= targets
    bad_all &= targets
    res = {
        "files": len(files),
        "emcc_exit": dict(rcs),
        "target_functions": len(targets),
        "target_defined": len(defined),
        "functions_pass": len(defined - bad_all),
        "functions_with_error": len(bad_all & defined),
        "error_lines": errs["errors"],
        "global_error_lines": errs["global"],
        "unattributed_error_lines": errs["unattributed"],
        "failclosed_files": failclosed_files,
        "emcc_seconds_sum": round(seconds, 2),
        "wall_seconds": round(time.time() - t_all, 2),
    }
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
