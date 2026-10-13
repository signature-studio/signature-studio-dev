"""Fruity Wrapper (block19091/23676) を RetDec で関数単位に lift し、成否を集計する (#828 受入条件 1)。

使い方 (cwd=リポジトリルート):
  FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/retdec_batch.py [block19091_PE.bin ...]
出力: tools/hostbridge/wrapper_lift/work/retdec_<block>.json (gitignore。commit しない)
方式:
  - 関数範囲 (measure_decode.py と同じ chain 併合の関数集合) を BATCH 個ずつ `--select-ranges` で渡す。
    `--select-decode-only` を使う (RetDec 全体は単一 range でも decode 段で落ちるため。REPORT §2)。
  - 成功 = 出力 C に関数 `function_<開始VA>` の定義 (`{` で始まる本体) が現れること。
  - 失敗したバッチは 2 分割を再帰して、失敗関数 (単独 range で失敗) を特定する。
"""
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
RETDEC = os.environ.get("RETDEC", "/opt/retdec/bin/retdec-decompiler")
BATCH = int(os.environ.get("BATCH", "500"))
TMP = os.path.join(WORK, "retdec_tmp")
DEF_RE = re.compile(r"^[^\s/][^;=]*\bfunction_([0-9a-f]+)\s*\([^;]*\)\s*\{", re.M)


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


def run_ranges(path, rngs, tag):
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, tag + ".c")
    arg = ",".join("0x%x-0x%x" % (b, e) for (b, e) in rngs)
    t0 = time.time()
    p = subprocess.run(
        [RETDEC, "-s", "-o", out, "--select-ranges", arg, "--select-decode-only", path],
        capture_output=True, text=True, timeout=900,
    )
    dt = time.time() - t0
    defined = set()
    if p.returncode == 0 and os.path.exists(out):
        with open(out, errors="replace") as fh:
            for m in DEF_RE.finditer(fh.read()):
                defined.add(int(m.group(1), 16))
        os.remove(out)
    return p.returncode, dt, defined


def lift_set(path, rngs, tag, stats):
    rc, dt, defined = run_ranges(path, rngs, tag)
    if rc == 0:
        ok = [r for r in rngs if r[0] in defined]
        miss = [r for r in rngs if r[0] not in defined]
        stats["ok"] += len(ok)
        stats["fail"] += len(miss)
        stats["seconds"] += dt
        stats["batches"] += 1
        for (b, e) in miss:
            stats["failed"].append({"func": "0x%x" % b, "end": "0x%x" % e, "reason": "no_definition"})
        return
    if len(rngs) == 1:
        stats["fail"] += 1
        stats["failed"].append({"func": "0x%x" % rngs[0][0], "end": "0x%x" % rngs[0][1]})
        return
    mid = len(rngs) // 2
    lift_set(path, rngs[:mid], tag + "a", stats)
    lift_set(path, rngs[mid:], tag + "b", stats)


def measure(name):
    path = os.path.join(FL, name)
    img = Image(path)
    rngs = funcs_of(img)
    stats = {"ok": 0, "fail": 0, "seconds": 0.0, "batches": 0, "failed": []}
    t0 = time.time()
    for i in range(0, len(rngs), BATCH):
        lift_set(path, rngs[i:i + BATCH], "%s_%d" % (name.split("_")[0], i), stats)
    res = {
        "file": name,
        "funcs": len(rngs),
        "lift_ok": stats["ok"],
        "lift_fail": stats["fail"],
        "lift_ok_ratio": round(stats["ok"] / len(rngs), 4) if rngs else None,
        "batch_size": BATCH,
        "retdec_seconds_sum": round(stats["seconds"], 2),
        "wall_seconds": round(time.time() - t0, 2),
        "failed_funcs": stats["failed"][:200],
        "failed_count": len(stats["failed"]),
        "retdec": RETDEC,
    }
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "retdec_%s.json" % name.split("_")[0]), "w") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k != "failed_funcs"}, ensure_ascii=False))


if __name__ == "__main__":
    names = sys.argv[1:] or ["block19091_PE.bin"]
    for n in names:
        measure(n)
