#!/usr/bin/env python3
"""P20 (#2963): Fresh Air GainDsp::process の x64c wasm を、実機機械語 (native_runner) と同じシナリオで突き合わせる。

  python3 tools/perf/p20/fa_native_diff.py [--n 400] [--seed 64030] [--out tools/perf/p20/work/fa/diff]

- シナリオ生成・native 実行は tools/liftlib/liftlib/harness の spec.py / diff.py を使う (liftlib の FA spec をそのまま使う)。
- wasm 側は fa_wasm_runner.mjs (liftlib の wasm_runner.mjs の x64c 版)。
- 比較は liftlib diff.run_diff と同じ粒度: 各シナリオの各バッファの (hex, ポインタ token) が一致するか。
- 前提: tools/targets/freshair/work/win/ (fetch.sh の展開物) と tools/perf/p20/work/fa/fa.cjs (build_fa_gain.sh の出力)。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "liftlib"))
from liftlib.harness import diff as D  # noqa: E402
from liftlib.harness import spec as SP  # noqa: E402

IMAGE = os.path.join(ROOT, "tools", "targets", "freshair", "work", "win", "Fresh Air",
                     "C__ProgramData_Slate Digital", "Fresh Air", "SlateCore.core_64")
SPEC = os.path.join(ROOT, "tools", "liftlib", "specs", "fa_gain.json")
ENTRY_VA = 0x180AFE090


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=64030)
    ap.add_argument("--out", default=os.path.join(HERE, "work", "fa", "diff"))
    ap.add_argument("--cjs", default=os.path.join(HERE, "work", "fa", "fa.cjs"))
    ap.add_argument("--neg-wasm-seed", type=int, default=0,
                    help="ネガティブコントロール: wasm 側だけ別 seed のシナリオを流す (FAIL になることを確認する)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    spec = json.load(open(SPEC))
    scen_txt = SP.build(spec, n=a.n, seed=a.seed)
    sp = os.path.join(a.out, "scen.txt")
    open(sp, "w").write(scen_txt)
    sp_w = sp
    if a.neg_wasm_seed:
        sp_w = os.path.join(a.out, "scen_neg.txt")
        open(sp_w, "w").write(SP.build(spec, n=a.n, seed=a.neg_wasm_seed))
    exe = D.build_native(a.out)
    nat = os.path.join(a.out, "out_native.txt")
    r = subprocess.run([exe, IMAGE, "%x" % ENTRY_VA, sp, nat], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise SystemExit("native runner rc=%d: %s" % (r.returncode, r.stderr[-500:]))
    sigp = os.path.join(a.out, "sig.json")
    json.dump([{"slot": 0, "ty": "i64"}, {"slot": 1, "ty": "i64"}], open(sigp, "w"))
    was = os.path.join(a.out, "out_wasm.txt")
    r = subprocess.run(["node", os.path.join(HERE, "fa_wasm_runner.mjs"), a.cjs, sigp, sp_w, was],
                       capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise SystemExit("wasm runner rc=%d: %s" % (r.returncode, r.stderr[-500:]))
    N, W = D.parse_out(nat), D.parse_out(was)
    keys = sorted(N)
    summ = dict(scenarios=len(set(k[0] for k in keys)), steps=len(keys), match=0, mismatch=0,
                native_crash=0, wasm_trap=0, bufs_compared=0)
    dead = set()
    for key in keys:
        s = key[0]
        if s in dead:
            continue
        na, wb = N[key], W.get(key)
        if na["crash"]:
            summ["native_crash"] += 1
            dead.add(s)
            continue
        if wb is None or wb["crash"]:
            summ["wasm_trap"] += 1
            summ["mismatch"] += 1
            dead.add(s)
            continue
        bad = [nm for nm, v in na["bufs"].items() if wb["bufs"].get(nm) != v]
        summ["bufs_compared"] += len(na["bufs"])
        if bad:
            summ["mismatch"] += 1
        else:
            summ["match"] += 1
    summ["neg_wasm_seed"] = a.neg_wasm_seed
    print(json.dumps(summ))


if __name__ == "__main__":
    main()
