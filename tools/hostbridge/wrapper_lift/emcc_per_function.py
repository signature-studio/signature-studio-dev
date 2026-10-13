"""生成 C を emcc -c で通し、関数単位の通過数を集計する (#1128 受入条件 1・2)。

使い方 (cwd=リポジトリルート):
  EM_CONFIG=<emsdk>/.emscripten PATH=<emsdk>/upstream/emscripten:$PATH \
    python3 tools/hostbridge/wrapper_lift/emcc_per_function.py <dir_or_file_c> [...] --targets <block.bin> --out <json>
入力: 1 ファイル = 1 emcc -c 呼び出し。ディレクトリ指定時は中の *.c を全部対象にする。
判定: error 行 (`file:line:col: error:`) を、その行を含む関数定義 `function_<hex>(...) {` に帰属させる。
  関数定義の外の error は global として別集計する (関数の通過判定には含めない)。
  通過 = 定義を持ち、本体内に error が無い関数。
出力: 関数数・通過数・error 行数・global error 数・所要秒・emcc 呼び出しの exit 内訳を JSON で書く。
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

DEF_RE = re.compile(r"^[^\s/][^;=]*\bfunction_([0-9a-f]+)\s*\([^;]*\)\s*\{", re.M)
ERR_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\d+: error: ", re.M)


def run_one(path, tmp_o, timeout, extra):
    t0 = time.time()
    try:
        p = subprocess.run(
            ["emcc", "-c", "-w", "-O0", "-fno-strict-aliasing", "-ferror-limit=0"] + extra + [path, "-o", tmp_o],
            capture_output=True, text=True, timeout=timeout,
        )
        rc, out = p.returncode, p.stderr + p.stdout
    except subprocess.TimeoutExpired:
        rc, out = None, ""
    return rc, out, time.time() - t0


def attribute(text, out, errs_out):
    defs = [(text.count("\n", 0, m.start()) + 1, int(m.group(1), 16)) for m in DEF_RE.finditer(text)]
    starts = [ln for ln, _ in defs]
    bad = set()
    for m in ERR_RE.finditer(out):
        if os.path.basename(m.group("file")) != os.path.basename(FILE_NOW[0]):
            continue
        line = int(m.group("line"))
        errs_out["errors"] += 1
        i = _bisect_right(starts, line) - 1
        if i < 0:
            errs_out["global"] += 1
        else:
            bad.add(defs[i][1])
    return bad


FILE_NOW = [""]


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
    seconds = 0.0
    t_all = time.time()
    tmpd = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    for f in files:
        with open(f, errors="replace") as fh:
            text = fh.read()
        FILE_NOW[0] = f
        rc, out, dt = run_one(f, os.path.join(tmpd, "o.o"), a.timeout, a.cflags.split())
        seconds += dt
        rcs[str(rc)] += 1
        defined |= {int(m.group(1), 16) for m in DEF_RE.finditer(text)}
        if rc != 0:
            bad_all |= attribute(text, out, errs)
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
        "emcc_seconds_sum": round(seconds, 2),
        "wall_seconds": round(time.time() - t_all, 2),
    }
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
