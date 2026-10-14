"""Fruity Wrapper (block19091/23676) を RetDec で関数単位に lift し、成否を集計する (#828 受入条件 1)。

使い方 (cwd=リポジトリルート):
  RETDEC=<retdec>/bin/retdec-decompiler FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/retdec_batch.py [block19091_PE.bin ...]
  RETDEC=<retdec>/bin/retdec-decompiler FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/retdec_batch.py --nc
出力: tools/hostbridge/wrapper_lift/work/retdec_<block>.json (gitignore。commit しない)
方式:
  - 関数範囲 (measure_decode.py と同じ chain 併合の関数集合) を BATCH 個ずつ `--select-ranges` で渡す。
    `--select-decode-only` を使う (RetDec 全体は単一 range でも decode 段で落ちるため。REPORT §2)。
  - 成功 = 出力 C に関数 `function_<開始VA>` の定義 (`{` で始まる本体) が現れること。
  - 失敗したバッチは 2 分割を再帰して、失敗関数 (単独 range で失敗) を特定する。
  - 失敗の reason: retdec_nonzero (単独 range で非 0 終了・err は RetDec のログ行)、
    retdec_timeout (TIMEOUT 秒超過)、no_definition (exit 0 だが定義なし)。
  - 所要: seconds_all = 全 RetDec 呼び出し (成功・失敗・分割前の親 batch を含む) の wall 時間の和。
    seconds_ok = rc == 0 の呼び出しだけの和。
--nc: 先頭 NC_N 関数の batch で 1 関数の定義ヘッダを出力 C から削除し、判定が no_definition に変わることを数値で示す。
"""
import collections
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "liftlib"))
from liftlib.pe import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
FL = os.environ["FL_WIN64_DIR"]
RETDEC = os.environ["RETDEC"]
BATCH = int(os.environ.get("BATCH", "500"))
TIMEOUT = int(os.environ.get("TIMEOUT", "300"))
NC_N = 20
TMP = os.path.join(WORK, "retdec_tmp")
KEEP_DIR = os.environ.get("KEEP_DIR", "")
DEF_RE = re.compile(r"^[^\s/][^\n;=]*\bfunction_([0-9a-f]+)\s*\([^\n;{}]*\)\s*\{", re.M)


def funcs_of(img):
    seen = set()
    out = []
    for (b, _e) in img.pdata_functions():
        rng = img.func_at(b, merge=True)
        if rng is None or rng in seen:
            continue
        seen.add(rng)
        out.append(rng)
    return out


RANGE_DEF_RE = re.compile(r"^// Address range: 0x([0-9a-f]+) - 0x[0-9a-f]+\n(?:    //[^\n]*\n)*?^[^\s/][^\n;=]*\b\w+\s*\([^\n;{}]*\)\s*\{", re.M)


def defined_in(text):
    return {int(m.group(1), 16) for m in DEF_RE.finditer(text)} | {int(m.group(1), 16) for m in RANGE_DEF_RE.finditer(text)}


def last_error(log):
    lines = [l.strip() for l in log.splitlines() if l.strip()]
    hits = [l for l in lines if l.startswith("[")]
    line = hits[-1] if hits else (lines[-1] if lines else "")
    return line[:200]


def new_stats():
    return {"ok": 0, "fail": 0, "seconds_all": 0.0, "seconds_ok": 0.0, "invocations": 0,
            "failed": [], "reasons": collections.Counter(), "errs": collections.Counter()}


def run_ranges(path, rngs, tag, stats):
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, tag + ".c")
    arg = ",".join("0x%x-0x%x" % (b, e) for (b, e) in rngs)
    t0 = time.time()
    rc, text, err = None, "", "timeout"
    try:
        p = subprocess.run(
            [RETDEC, "-s", "-o", out, "--select-ranges", arg, "--select-decode-only", path],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        rc = p.returncode
        err = last_error(p.stderr + "\n" + p.stdout)
        if rc == 0 and os.path.exists(out):
            with open(out, errors="replace") as fh:
                text = fh.read()
            if KEEP_DIR and text:
                os.makedirs(KEEP_DIR, exist_ok=True)
                with open(os.path.join(KEEP_DIR, tag + ".c"), "w") as fh:
                    fh.write(text)
    except subprocess.TimeoutExpired:
        pass
    finally:
        if os.path.exists(out):
            os.remove(out)
    dt = time.time() - t0
    stats["invocations"] += 1
    stats["seconds_all"] += dt
    if rc == 0:
        stats["seconds_ok"] += dt
    return rc, text, err


def record_fail(stats, b, e, reason, err=""):
    stats["fail"] += 1
    stats["reasons"][reason] += 1
    if err:
        stats["errs"][err] += 1
    stats["failed"].append({"func": "0x%x" % b, "end": "0x%x" % e, "reason": reason, "err": err})


def lift_set(path, rngs, tag, stats):
    rc, text, err = run_ranges(path, rngs, tag, stats)
    if rc == 0:
        defined = defined_in(text)
        missing = []
        for (b, e) in rngs:
            if b in defined:
                stats["ok"] += 1
            else:
                missing.append((b, e))
        if not missing:
            return
        if len(rngs) == 1:
            record_fail(stats, rngs[0][0], rngs[0][1], "no_definition")
            return
        # 直前範囲の終端が対象の開始と隣接すると、RetDec は対象を 1 バイト手前の VA 名で出すことがある (REPORT §10)。
        # 定義が出なかった範囲だけを再試行する (単独なら正しく出る)。
        if len(missing) < len(rngs):
            lift_set(path, missing, tag + "m", stats)
            return
        mid = len(rngs) // 2
        lift_set(path, rngs[:mid], tag + "a", stats)
        lift_set(path, rngs[mid:], tag + "b", stats)
        return
    if len(rngs) == 1:
        b, e = rngs[0]
        record_fail(stats, b, e, "retdec_timeout" if rc is None else "retdec_nonzero", err)
        return
    mid = len(rngs) // 2
    lift_set(path, rngs[:mid], tag + "a", stats)
    lift_set(path, rngs[mid:], tag + "b", stats)


def measure(name):
    path = os.path.join(FL, name)
    img = Image(path)
    rngs = funcs_of(img)
    stats = new_stats()
    t0 = time.time()
    for i in range(0, len(rngs), BATCH):
        lift_set(path, rngs[i:i + BATCH], "%s_%d" % (name.split("_")[0], i), stats)
    res = {
        "file": name,
        "funcs": len(rngs),
        "lift_ok": stats["ok"],
        "lift_fail": stats["fail"],
        "lift_ok_ratio": round(stats["ok"] / len(rngs), 4) if rngs else None,
        "fail_by_reason": dict(stats["reasons"]),
        "fail_err_hist": dict(stats["errs"].most_common(20)),
        "batch_size": BATCH,
        "retdec_invocations": stats["invocations"],
        "retdec_seconds_all": round(stats["seconds_all"], 2),
        "retdec_seconds_ok_calls": round(stats["seconds_ok"], 2),
        "wall_seconds": round(time.time() - t0, 2),
        "failed_funcs": stats["failed"][:200],
        "failed_count": len(stats["failed"]),
        "retdec": RETDEC,
    }
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "retdec_%s.json" % name.split("_")[0]), "w") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k != "failed_funcs"}, ensure_ascii=False))


def def_match(text, va):
    for rx in (DEF_RE, RANGE_DEF_RE):
        for m in rx.finditer(text):
            if int(m.group(1), 16) == va:
                return m
    return None


def nc_remove(text):
    before = defined_in(text)
    by_name = {int(m.group(1), 16) for m in DEF_RE.finditer(text)}
    by_range = {int(m.group(1), 16) for m in RANGE_DEF_RE.finditer(text)}
    va = min(by_range - by_name or before)
    m = def_match(text, va)
    text2 = text[:m.start()] + text[m.end():]
    after = defined_in(text2)
    return {
        "defined_before": len(before),
        "target": "0x%x" % va,
        "removed_header": m.group(0).strip(),
        "defined_after": len(after),
        "target_status_after": "ok" if va in after else "no_definition",
    }


def negative_control(name="block19091_PE.bin"):
    path = os.path.join(FL, name)
    rngs = funcs_of(Image(path))[:NC_N]
    stats = new_stats()
    rc, text, err = run_ranges(path, rngs, "nc", stats)
    if rc != 0:
        print(json.dumps({"nc": "retdec_failed", "rc": rc, "err": err}, ensure_ascii=False))
        return
    res = nc_remove(text)
    res["batch_funcs"] = len(rngs)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    if "--nc" in sys.argv:
        negative_control()
    else:
        names = [a for a in sys.argv[1:]] or ["block19091_PE.bin"]
        for n in names:
            measure(n)
