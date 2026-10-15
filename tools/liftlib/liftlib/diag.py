"""diag.py — silent miscompile の原因示唆 (CAB-55)。

diagnose(cfg_path):
  1. ベースライン (全 pass 有効) を差分ハーネスで評価
  2. 適用された修復種 (p1/f7/f2) ごとに「その pass だけ無効」で再ビルド→再評価 (対照実験)
       → ベースライン一致 かつ 無効化で不一致 = その pass が必須 (修復が効いている)
  3. 全 pass 有効でも不一致が残る場合: 未修復の検出器所見 (dropped load / dropped branch / xmm 引数) を列挙し,
     最初の不一致バッファとオフセットを添えて「疑わしい pass」を示す
"""
import copy
import json
import os
from typing import Any

from . import pipeline
from .harness import diff as D


def _evaluate(cfg: dict[str, Any], workdir_name: str, passes_override: dict[str, bool],
              n: int | None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    c = copy.deepcopy(cfg)
    c["name"] = workdir_name
    c["passes"] = dict(c.get("passes", {}))
    c["passes"].update(passes_override)
    base_name = cfg["name"]
    c["raw_ll"] = os.path.join(pipeline.HERE, "..", "work", base_name, base_name + ".drc.ll")
    tmp = os.path.join(pipeline.HERE, "..", "work", workdir_name + "_cfg.json")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    json.dump(c, open(tmp, "w"))
    cfg2, wd, cjs, stats, log = pipeline.run_all(tmp)
    spec = json.load(open(os.path.join(pipeline.HERE, "..", c["spec"])))
    img = pipeline.rpath(c["image"])
    assert img is not None, "diag: image path が解決できない (cfg[image])"
    s = D.run_diff(img, int(c["func_va"], 16), spec, cjs, os.path.join(wd, workdir_name + "_fixed.ll"), c["wasm_func"],
                   os.path.join(wd, "diff"), n=n, timeout=60)
    return s, stats, log


def diagnose(cfg_path: str, n: int | None = None) -> dict[str, Any]:
    cfg = pipeline.load_cfg(cfg_path)
    out: dict[str, Any] = dict(target=cfg["name"])
    base_s, base_stats, base_log = _evaluate(cfg, cfg["name"] + "_diag_base", {}, n)
    out["baseline"] = D.fmt(base_s)
    out["baseline_mismatch"] = base_s["mismatch"]
    out["ablation"] = {}
    applied: dict[str, Any] = {
        "p1": base_stats.get("p1", {}).get("reconstructed", 0) + base_stats.get("p1", {}).get("rewired", 0),
        "f7": base_stats.get("f7", {}).get("repaired", 0),
        "f2": base_stats.get("f2", {}).get("sites_fixed", 0) + base_stats.get("f2", {}).get("callee_fixed", 0),
    }
    out["applied"] = applied
    for p, cnt in applied.items():
        if not cnt:
            continue
        s, _st, _lg = _evaluate(cfg, cfg["name"] + "_diag_no_" + p, {p: False}, n)
        necessary = s["mismatch"] > base_s["mismatch"]
        out["ablation"][p] = dict(result=D.fmt(s), necessary=necessary)
    if base_s["mismatch"]:
        out["suspects"] = []
        for k, v in base_stats.items():
            if isinstance(v, dict) and (v.get("unsupported") or v.get("unbound") or v.get("no_user")):
                out["suspects"].append("%s: unrepaired findings %s" % (k, {a: b for a, b in v.items() if a in ("unsupported", "unbound", "no_user")}))
        out["first_mismatch"] = base_s["details"][:2]
    return out
