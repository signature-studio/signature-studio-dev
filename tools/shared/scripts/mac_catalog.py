#!/usr/bin/env python3
"""mac .app 内の全 Mach-O (fat/thin) を列挙し、x86_64 スライスを work/slices に抽出、
   LC_ID_DYLIB・依存 dylib・export 数を data/mac_macho_catalog.json に保存"""
import sys, os, json, struct, subprocess
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from common import *

def is_macho(p):
    try:
        with open(p, "rb") as f: h = f.read(4)
    except Exception: return False
    return h in (b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")

def scan(p):
    rel = os.path.relpath(p, MAC_APP)
    try:
        s = fat_slice(p, "x86_64", out=os.path.join(WORK, "slices_all", rel.replace("/", "__")))
    except Exception as e:
        return {"path": rel, "error": str(e)}
    r = {"path": rel, "size": os.path.getsize(p), "slice": s}
    out = run(["llvm-otool", "-L", s]).stdout.splitlines()[1:]
    r["deps"] = [l.strip().split(" (")[0] for l in out]
    nm = run(["llvm-nm", "-gU", s]).stdout.splitlines()
    r["n_exports"] = len(nm)
    return r

if __name__ == "__main__":
    files = []
    for root, ds, fs in os.walk(MAC_APP):
        if "Python.framework" in root and "/lib/" in root: continue
        for f in fs:
            p = os.path.join(root, f)
            if os.path.islink(p) or os.path.getsize(p) < 4096: continue
            if is_macho(p): files.append(p)
    print(len(files), "Mach-O files")
    with Pool(10) as pool:
        res = pool.map(scan, sorted(files), chunksize=2)
    json.dump(res, open(f"{RAW}/mac_macho_catalog.json", "w"))
    print("saved", sum(1 for r in res if "error" in r), "errors")
