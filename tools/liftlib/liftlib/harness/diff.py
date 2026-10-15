"""diff.py — 汎用差分ハーネス (CAB-55): 実機機械語 (VA 敷設・ms_abi 直接実行) vs lift→wasm を乱数 context で比較。

  run_diff(image, func_va, spec, cjs, ll_path, wasm_func, out_dir) -> dict
    1. spec からシナリオ生成 (spec.build) 2. native ランナー実行 3. wasm ランナー (node) 実行 4. バッファ単位で bit 比較
  比較対象: spec の全バッファ (guard 64B 含む; ポインタ欄は (バッファ名+オフセット) トークンで比較)。
"""
import json
from typing import Any
import os
import re
import subprocess

from .. import env, ir as IR
from . import spec as SP

HERE = os.path.dirname(os.path.abspath(__file__))


def build_native(out_dir):
    exe = os.path.join(out_dir, "native_runner")
    srcs = [os.path.join(HERE, "native_runner.c"), os.path.join(HERE, "ms_call.S")]
    if os.path.exists(exe) and all(os.path.getmtime(exe) >= os.path.getmtime(s) for s in srcs):
        return exe
    r = subprocess.run(["gcc", "-O1", "-o", exe] + srcs, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("native runner build failed:\n" + r.stderr[-2000:])
    return exe


def wasm_sig(ll_path, fname):
    """最終 IR の define から wasm 関数の引数列 (slot / xmm 番号と型) を得る。"""
    mod = IR.Module.load(ll_path)
    fn = mod.func(fname)
    if fn is None:
        raise RuntimeError("function %s not in %s" % (fname, ll_path))
    sig = []
    for ty, nm in fn.params():
        m = re.match(r"%arg(\d+)$", nm)
        if m:
            sig.append(dict(slot=int(m.group(1)) - 1, ty=ty))
            continue
        m = re.match(r"%xmm(\d+)_bits$", nm)
        if m:
            sig.append(dict(xmm=int(m.group(1)), ty=ty))
            continue
        raise RuntimeError("unrecognized param %s %s" % (ty, nm))
    return sig


def run_wasm(cjs, wasm_func, sig_path, scen_path, out_path, timeout=240):
    """wasm 側だけを走らせて出力 (out_path) を作る (署名ガード用; native 不要)。正常 True / タイムアウト False。"""
    try:
        r = env.run(["node", os.path.join(HERE, "wasm_runner.mjs"), cjs, wasm_func, sig_path, scen_path, out_path],
                    capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        open(out_path, "w").close()
        return None
    if r.returncode:
        raise RuntimeError("wasm runner rc=%d: %s" % (r.returncode, r.stderr[-800:]))
    return True


def parse_out(path):
    res = {}
    cur = None
    for ln in open(path):
        ln = ln.rstrip("\n")
        if ln.startswith("R "):
            w = ln.split()
            cur = (int(w[1]), int(w[2]))
            res[cur] = dict(crash=int(w[3]), rax=w[4], xmm0=w[5] if len(w) > 5 else "0" * 16, bufs={})
        elif ln.startswith("D ") and cur is not None:
            w = ln.split(" ")
            res[cur]["bufs"][w[1]] = (w[2], w[3] if len(w) > 3 else "-")
    return res


def run_diff(image: str, func_va: int, spec: dict[str, Any], cjs: str | None, ll_path: str, wasm_func: str,
             out_dir: str, n: int | None = None, seed: int | None = None, verbose: bool = False,
             timeout: int = 240) -> dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    scen_txt = SP.build(spec, n=n, seed=seed)
    sp = os.path.join(out_dir, "scen.txt")
    open(sp, "w").write(scen_txt)
    exe = build_native(out_dir)
    nat = os.path.join(out_dir, "out_native.txt")
    was = os.path.join(out_dir, "out_wasm.txt")
    r = subprocess.run([exe, image, "%x" % func_va, sp, nat], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError("native runner rc=%d: %s" % (r.returncode, r.stderr[-500:]))
    sigp = os.path.join(out_dir, "sig.json")
    json.dump(wasm_sig(ll_path, wasm_func), open(sigp, "w"))
    hang = False
    try:
        if cjs is None:                       # 型: build 前 (detect_only) の cfg では cjs が無い — 呼ぶ側の誤り
            raise ValueError("run_diff: cjs is required (wasm CJS path)")
        r = env.run(["node", os.path.join(HERE, "wasm_runner.mjs"), cjs, wasm_func, sigp, sp, was],
                    capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError("wasm runner rc=%d: %s" % (r.returncode, r.stderr[-800:]))
    except subprocess.TimeoutExpired:
        hang = True
        open(was, "a").close()
    N, W = parse_out(nat), (parse_out(was) if os.path.exists(was) else {})
    nscen = len(set(k[0] for k in N))
    cmp_ret = spec.get("compare_ret", False)
    ret_xmm0 = spec.get("ret_from_xmm0", False)      # wasm の i64 戻り = xmm0 下位 64bit (leafabi)
    ign = set(spec.get("ignore_buffers", []))
    summ: dict[str, Any] = dict(scenarios=nscen, steps=len(N), match=0, mismatch=0, native_crash=0, wasm_trap=0,
                                wasm_hang=hang, mismatch_scen=set(), details=[])
    dead: set[str] = set()
    for key in sorted(N):
        s = key[0]
        if s in dead:
            continue
        a, b = N[key], W.get(key)
        if a["crash"]:
            summ["native_crash"] += 1
            dead.add(s)
            continue
        if b is None or b["crash"]:
            summ["wasm_trap"] += 1
            summ["mismatch"] += 1
            summ["mismatch_scen"].add(s)
            dead.add(s)
            if len(summ["details"]) < 5:
                summ["details"].append(dict(scen=s, step=key[1], why="wasm trap"))
            continue
        bad = []
        for nm, (hx, tok) in a["bufs"].items():
            if nm in ign:
                continue
            hb, tb = b["bufs"].get(nm, ("", "-"))
            for (o, n_) in spec.get("mask_ranges", {}).get(nm, []):     # 環境依存値 (vtable の絶対 VA 等) を比較から除く
                hx = hx[:2 * o] + "00" * n_ + hx[2 * (o + n_):]
                hb = hb[:2 * o] + "00" * n_ + hb[2 * (o + n_):]
            if hx != hb or tok != tb:
                A = bytes.fromhex(hx)
                Bv = bytes.fromhex(hb) if hb else b""
                offs = [i for i in range(min(len(A), len(Bv))) if A[i] != Bv[i]]
                bad.append((nm, offs[:6], len(offs), tok != tb))
        if cmp_ret and a["rax"] != b["rax"]:
            bad.append(("<rax>", [], 1, False))
        if ret_xmm0:
            # ret_bits=32: f32 戻りは xmm0 の下位 32bit のみ有意 (上位は native では残骸)
            nb = int(spec.get("ret_bits", 64)) // 4
            if a["xmm0"][:16][16 - nb:] != b["rax"][16 - nb:]:
                bad.append(("<xmm0>", [], 1, False))
        if bad:
            summ["mismatch"] += 1
            summ["mismatch_scen"].add(s)
            if len(summ["details"]) < 5:
                summ["details"].append(dict(scen=s, step=key[1], bad=bad[:4]))
        else:
            summ["match"] += 1
    summ["mismatch_scen"] = sorted(summ["mismatch_scen"])
    return summ


def fmt(summ: dict[str, Any]) -> str:
    return "scenarios=%d steps=%d match=%d mismatch=%d native_crash=%d wasm_trap=%d%s" % (
        summ["scenarios"], summ["steps"], summ["match"], summ["mismatch"], summ["native_crash"], summ["wasm_trap"],
        " WASM-HANG(timeout)" if summ.get("wasm_hang") else "")
