#!/usr/bin/env python3
# coef_trace.c の出力 (SC/KH) を係数計算 1 call ごとに束ね、係数出力 (coef_probe の E 行) と照合する。
#   usage: python3 ks_coef_trace_cmp.py sc_trace.txt kh_trace.txt sc_coef.txt kh_coef.txt
# 出力: 係数出力が最初に食い違う call について、両側の子呼出し (名前・戻り値) を並べる。
import sys
from collections import defaultdict


def parse_trace(path):
    calls = []
    cur = None
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == "P":
            cur = None
            continue
        if t[0] == "C" and t[1] == "COEF":
            cur = {"in": line.strip(), "sub": []}
            calls.append(cur)
        elif t[0] in ("C", "R") and cur is not None and t[1] != "COEF":
            cur["sub"].append(line.strip())
        elif t[0] == "R" and t[1] == "COEF" and cur is not None:
            cur["out"] = line.strip()
    return calls


def parse_coef(path):
    out = []
    for line in open(path):
        if line.startswith("E "):
            blk = line.rsplit("blk=", 1)[1].strip()
            out.append(blk)
    return out


def main():
    sc_t, kh_t, sc_c, kh_c = sys.argv[1:5]
    st = parse_trace(sc_t)
    kt = parse_trace(kh_t)
    sb = parse_coef(sc_c)
    kb = parse_coef(kh_c)
    print(f"coef calls: trace SC={len(st)} KH={len(kt)}; block SC={len(sb)} KH={len(kb)}")
    n = min(len(sb), len(kb), len(st), len(kt))
    for i in range(n):
        if sb[i] != kb[i]:
            print(f"first output mismatch: coef call #{i}")
            print("  SC in :", st[i]["in"])
            print("  KH in :", kt[i]["in"])
            print("  SC sub:")
            for s in st[i]["sub"]:
                print("   ", s)
            print("  KH sub:")
            for s in kt[i]["sub"]:
                print("   ", s)
            return
    print("no output mismatch within common calls")


if __name__ == "__main__":
    main()
