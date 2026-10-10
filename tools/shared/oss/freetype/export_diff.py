#!/usr/bin/env python3
"""元バイナリ (mac libfreetype_x64.dylib / win freetype.dll) の export と再ビルド libfreetype.a の定義シンボルを比較する。"""
import sys, os, subprocess, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))
from common import *
mac = fat_slice(f"{MAC_SHARED}/libfreetype_x64.dylib")
mac_ex = {l.split()[-1].lstrip("_") for l in run(["llvm-nm", "-gU", mac]).stdout.splitlines() if l.strip()}
win = {r["file"]: r for r in json.load(open(f"{RAW}/win_pe_catalog.json"))}["block24359_PE.bin"]["exports"]
a = f"{WORK}/build/freetype/wasm32/src/objs/.libs/libfreetype.a"
defd = set()
for l in run(["llvm-nm", "--defined-only", "-g", a]).stdout.splitlines():
    p = l.split()
    if len(p) >= 3 and p[-2] in ("T", "D", "R", "B"): defd.add(p[-1])
res = {}
for name, ex in (("mac libfreetype_x64.dylib", mac_ex), ("win freetype.dll", set(win))):
    ex = {e for e in ex if e}
    miss = sorted(e for e in ex if e not in defd)
    res[name] = {"exports": len(ex), "covered": len(ex) - len(miss), "missing": miss}
    print(f"{name}: exports={len(ex)} covered_by_rebuild={len(ex)-len(miss)} missing={len(miss)} {miss[:17]}")
json.dump(res, open(f"{DATA}/freetype_export_diff.json", "w"), indent=1)
