#!/usr/bin/env python3
"""全 win PE に ipp_win_scan.analyze を適用し data/ipp_win_usage.json に保存。"""
import sys, os, json, glob
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import ipp_win_scan

def work(f):
    try:
        r = ipp_win_scan.analyze(f)
    except Exception as e:
        return os.path.basename(f), {"error": str(e)}
    return os.path.basename(f), {"entries": len(r), "table": r}

if __name__ == "__main__":
    files = sorted(glob.glob(f"{WIN_EXTRACTED}/block*_PE.bin"))
    cat = {r["file"]: r for r in json.load(open(f"{RAW}/win_pe_catalog.json"))}
    # 事前フィルタ: UTF-16/ASCII の 'ippMalloc' を含むもののみ
    cand = []
    pat8, pat16 = b"ippMalloc", "ippMalloc".encode("utf-16le")
    for f in files:
        d = open(f, "rb").read()
        if (pat8 in d or pat16 in d) and cat[os.path.basename(f)].get("dllname") not in ("dsp_ippv2.dll", "dsp_ippv2_x64.dll"):
            cand.append(f)
    print(len(cand), "PE with ipp loader table candidate")
    with Pool(12) as p:
        res = dict(p.map(work, cand, chunksize=2))
    json.dump(res, open(f"{RAW}/ipp_win_usage.json", "w"))
    print("done", sum(1 for v in res.values() if "error" in v), "errors")
