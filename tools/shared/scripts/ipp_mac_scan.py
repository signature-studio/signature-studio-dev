#!/usr/bin/env python3
"""mac (FPC) Mach-O x86_64 から dsp_ippv2 ローダ表を静的抽出し、各 IPP var の参照数を実測。
   ローダ idiom (FLEngine 0x5ba7c2 付近): lea rsi,[VAR]; xor cl,cl; lea rdx,[LIT]; mov rdi,rbp; call LoadProc
   LIT = FPC UnicodeString (len は lit-8 の qword)。 var 参照は rip 相対オペランドの厳密一致のみ数える。"""
import sys, os, json, struct, glob
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from macho_util import MachO

def analyze(path):
    m = MachO(path); d = m.d
    tx = m.section("__TEXT", "__text")
    if not tx: return None
    t0, tsz, tva = tx[4], tx[3], tx[2]
    arr = np.frombuffer(d, dtype=np.uint8, count=tsz, offset=t0)
    n = len(arr) - 20
    # lea rsi,[rip+x] (48 8D 35) ; xor cl,cl (30 C9) ; lea rdx,[rip+y] (48 8D 15)
    mk = ((arr[:n] == 0x48) & (arr[1:n+1] == 0x8D) & (arr[2:n+2] == 0x35) &
          (arr[7:n+7] == 0x30) & (arr[8:n+8] == 0xC9) &
          (arr[9:n+9] == 0x48) & (arr[10:n+10] == 0x8D) & (arr[11:n+11] == 0x15))
    table = []
    for i in np.where(mk)[0]:
        o = t0 + int(i); va = tva + int(i)
        var = va + 7 + struct.unpack_from("<i", d, o + 3)[0]
        lit = va + 16 + struct.unpack_from("<i", d, o + 12)[0]
        lo = m.va2off(lit)
        if lo is None or lo < 24: continue
        ln = struct.unpack_from("<q", d, lo - 8)[0]
        if not (0 < ln < 80): continue
        try: name = d[lo:lo + ln * 2].decode("utf-16le")
        except Exception: continue
        if name.startswith("ipp"): table.append((name, var, va))
    refs = {}
    for name, var, site in table: refs.setdefault(var, {"names": [], "call": 0, "mov": 0, "lea": 0, "other": 0})["names"].append(name)
    if refs:
        pos = np.where((arr[:-4] & 0xC7) == 0x05)[0] + 1
        pos = pos[pos + 4 < len(arr)]
        bb = [arr[pos + k].astype(np.int64) for k in range(4)]
        rel = bb[0] | (bb[1] << 8) | (bb[2] << 16) | (bb[3] << 24)
        rel = np.where(rel >= 2**31, rel - 2**32, rel)
        va0 = tva + pos
        varset = np.array(sorted(refs), dtype=np.int64)
        loader_sites = {s for _, _, s in table}
        for k in (0, 1, 2, 4):
            tg = va0 + 4 + k + rel
            for j in np.where(np.isin(tg, varset))[0]:
                p = int(pos[j]); v = int(tg[j]); op = int(arr[p-2]); mr = int(arr[p-1]); site = int(va0[j]) - 2
                if op == 0xFF and (mr & 0x38) in (0x10, 0x18, 0x20): kind = "call" if k == 0 else "other"
                elif op in (0x8B, 0x89, 0x3B, 0x39): kind = "mov"
                elif op == 0x8D:
                    kind = "lea"
                    if any(0 <= (site - s) <= 4 for s in loader_sites): continue
                else: kind = "other"
                refs[v][kind] += 1
    out = []
    for name, var, site in table:
        r = refs[var]
        out.append({"name": name, "var": hex(var), "call": r["call"], "mov": r["mov"], "lea": r["lea"], "other": r["other"]})
    return out

def work(rec):
    try:
        r = analyze(rec["slice"])
    except Exception as e:
        return rec["path"], {"error": repr(e)}
    return rec["path"], {"entries": len(r) if r is not None else -1, "table": r or []}

if __name__ == "__main__":
    cat = json.load(open(f"{RAW}/mac_macho_catalog.json"))
    cand = []
    pat = "ippMalloc".encode("utf-16le")
    for r in cat:
        if "slice" not in r: continue
        if pat in open(r["slice"], "rb").read() and not r["path"].endswith("dsp_ippv2_x64.dylib"): cand.append(r)
    print(len(cand), "Mach-O with ipp loader candidate")
    with Pool(12) as p:
        res = dict(p.map(work, cand))
    json.dump(res, open(f"{RAW}/ipp_mac_usage.json", "w"))
    import collections
    print("entries hist", collections.Counter(v.get("entries") for v in res.values()))
    print("errors", [k for k, v in res.items() if "error" in v][:5])
