#!/usr/bin/env python3
"""node と Chrome の pyscript 実行結果の一致を、JS とは別実装 (python) で検算する (PY-11 / #466)。
  python3 tests/pyscript_compare.py work/pyscript_node.json work/pyscript_chrome.json [--neg]
入力は `pyscript_e2e.mjs --dump` と `pyscript_browser.mjs --dump` の JSON。
検査: (1) check 名と ok が両環境で完全一致・全 PASS  (2) run_pyscript の出力 (outputs) が全件、キー順非依存の正規化 JSON で bit 一致
      (3) Chrome の Euclidean 出力を python で再計算 (整数算術) した onset 集合と照合 (JS oracle とは別実装)
--neg: Chrome 側 outputs の 1 ノートの time を +1 して比較し、不一致を検出 (exit 1) することを確認する。通常実行は不一致で exit 1。
"""
import json, sys, copy

def canon(x): return json.dumps(x, sort_keys=True, separators=(",", ":"))

def euclid(p, o, off):
    base = [o > 0 and (i == 0 or (i * o) // p != ((i - 1) * o) // p) for i in range(p)]
    return {j for j in range(p) if o > 0 and base[(j - off) % p]}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    neg = "--neg" in sys.argv
    node, chrome = (json.load(open(a)) for a in args[:2])
    if neg:
        for o in chrome["outputs"]:
            ns = o["result"]["score"]["notes"] if isinstance(o["result"], dict) and "score" in o["result"] else []
            if ns: ns[0]["time"] += 1; break
    fails = []
    # (1)
    nr = {r["name"]: r["ok"] for r in node["results"]}; cr = {r["name"]: r["ok"] for r in chrome["results"]}
    if nr != cr: fails.append(f"check 名/ok 不一致: node-only={sorted(set(nr)-set(cr))} chrome-only={sorted(set(cr)-set(nr))}")
    bad = [k for k, v in cr.items() if not v]
    if bad: fails.append(f"Chrome で FAIL: {bad}")
    # (2)
    no, co = node["outputs"], chrome["outputs"]
    if len(no) != len(co): fails.append(f"outputs 件数 node={len(no)} chrome={len(co)}")
    diff = [i for i, (a, b) in enumerate(zip(no, co)) if canon(a) != canon(b)]
    if diff: fails.append(f"outputs 不一致 {len(diff)}/{min(len(no),len(co))} 件 (index {diff[:5]}, name {[co[i]['name'] for i in diff[:5]]})")
    names = sorted({o["name"] for o in co if o["name"] != "EuclideanMut"})  # EuclideanMut = シナリオ内ネガコン NEG-a の改変版
    if names != ["Arpeggiator", "Euclidean", "Humanize", "Repeater", "Selector"]: fails.append(f"Chrome で実行された Piano roll script が 5 本でない: {names}")
    # (3)
    eu = [o for o in co if o["name"] == "Euclidean"]
    n_eu = 0
    for o in eu:
        v = o["values"]
        if not v: p, spec = 32, [(8, 0, 36), (13, 0, 37), (18, 0, 42)]
        else: p, spec = v["Pattern Length"], [(v[f"CH{c}: Onsets"], v[f"CH{c}: Offset"], v[f"CH{c}: Note #"]) for c in (1, 2, 3)]
        got = sorted((n["time"], n["number"]) for n in o["result"]["score"]["notes"])
        exp = sorted((j * 24, num) for (on, off, num) in spec for j in euclid(p, on, off))
        n_eu += 1
        if got != exp: fails.append(f"Euclidean 再計算不一致 p={p}: {len(got)} vs {len(exp)}")
    if n_eu == 0: fails.append("Euclidean 出力が無い")
    print(json.dumps({"node_env": node.get("env"), "chrome_env": chrome.get("env"), "checks": len(cr), "checks_pass": sum(cr.values()),
                      "scripts_run": names, "outputs": len(co), "outputs_mismatch": len(diff), "euclidean_recomputed": n_eu, "neg": neg, "fails": fails}, ensure_ascii=False))
    sys.exit(1 if fails else 0)
main()
