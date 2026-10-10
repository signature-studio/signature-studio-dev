#!/usr/bin/env python3
"""mac Mach-O 内の静的リンク IPP を symbol table から検出 (CPU dispatch prefix 付き: y8_ n8_ e9_ l9_ k0_ …)。
   -> data/ipp_static_mac.json : {file: {public: [...], n_own: N, n_syms: N}}"""
import sys, os, json, re
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from common import *
PFX = re.compile(r"^_?([a-z]\d)_(ipp[sicm]\w+|ownipp\w+|ippGet\w+|ippSet\w+|ippInit\w+|ippcore\w+)$")
PUB = re.compile(r"^_?(ipp[sicmw]\w+|ippGet\w+|ippSet\w+|ippInit\w+|ippMalloc|ippFree)$")
def work(rec):
    s = rec["slice"]
    out = run(["llvm-nm", "-a", s]).stdout.splitlines()
    pub = set(); own = 0; cpus = set(); n = 0
    for l in out:
        p = l.split()
        if len(p) < 3: continue
        nm = p[-1]; m = PFX.match(nm)
        if m:
            n += 1; cpus.add(m.group(1))
            if m.group(2).startswith("own"): own += 1
            else: pub.add(m.group(2))
        elif PUB.match(nm) and p[-2] in ("T", "t"):
            n += 1; pub.add(PUB.match(nm).group(1))
    return rec["path"], {"public": sorted(pub), "n_own": own, "n_syms": n, "cpus": sorted(cpus)}
if __name__ == "__main__":
    cat = json.load(open(f"{RAW}/mac_macho_catalog.json"))
    recs = [r for r in cat if "slice" in r and not r["path"].endswith("dsp_ippv2_x64.dylib")]
    with Pool(12) as p: res = dict(p.map(work, recs))
    res = {k: v for k, v in res.items() if v["n_syms"]}
    json.dump(res, open(f"{RAW}/ipp_static_mac.json", "w"), indent=1)
    for k, v in sorted(res.items()): print(k, v["n_syms"], len(v["public"]), v["n_own"], v["cpus"])
