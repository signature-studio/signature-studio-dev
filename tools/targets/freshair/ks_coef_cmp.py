#!/usr/bin/env python3
"""ks_coef_cmp.py <sc_coef.txt> <kh_coef.txt> — 係数計算関数 (SC 0x180b7fa80 / KH 0x180469d40) の呼出し引数と出口の係数ブロックを両側で比べる。
入力は lift2/native/coef_probe.c の出力 ("P <sidx> <call>" で処理 call を区切り、"E ty= o2= f= q= g= sr= blk=<hex>" が係数計算 1 回)。
判定: 入力 (ty/o2/f/q/g/sr) の bit 一致、出力ブロック (float32 語) の bit 一致と相対差 |SC−KH|/|KH| の分布。"""
import math
import struct
import sys
from collections import defaultdict

def parse(path):
    groups = defaultdict(list); pre = {}; key = None
    for line in open(path):
        t = line.split()
        if not t: continue
        if t[0] == "P": key = (int(t[1]), int(t[2])); groups[key]
        elif t[0] == "I" and key is not None:
            pre.setdefault(key, []).append(t[1].split("=", 1)[1])
        elif t[0] == "E" and key is not None:
            d = dict(x.split("=", 1) for x in t[1:])
            d["pre"] = pre.get(key, [""])[len(groups[key])] if len(pre.get(key, [])) > len(groups[key]) else ""
            groups[key].append(d)
    return groups

def fl(h): return struct.unpack("<f", bytes.fromhex(h))[0]

def rel(a, b):
    if math.isnan(a) or math.isnan(b): return math.inf
    if b == 0.0: return 0.0 if a == 0.0 else math.inf
    return abs(a - b) / abs(b)

BUCKETS = [("bit一致", 0.0), ("<=1e-6", 1e-6), ("<=1e-4", 1e-4), ("<=1e-3", 1e-3), ("<=1e-2", 1e-2), (">1e-2", math.inf)]

sc = parse(sys.argv[1]); kh = parse(sys.argv[2])
keys = sorted(set(sc) | set(kh))
n_grp = len(keys); cnt_diff_n = 0; n_rec = 0; in_bad = defaultdict(int); blk_bad_rec = 0
words = 0; word_bad = 0; dist = defaultdict(int); first = None
for k in keys:
    a = sc.get(k, []); b = kh.get(k, [])
    if len(a) != len(b):
        cnt_diff_n += 1
        if first is None: first = ("count", k, len(a), len(b))
    for ra, rb in zip(a, b):
        n_rec += 1
        for f in ("ty", "o2", "f", "q", "g", "sr"):
            if ra.get(f) != rb.get(f):
                in_bad[f] += 1
                if first is None: first = ("input", k, f, ra.get(f), rb.get(f))
        xa = bytes.fromhex(ra["blk"]); xb = bytes.fromhex(rb["blk"])
        if xa == xb: continue
        blk_bad_rec += 1
        for w in range(0, min(len(xa), len(xb)), 4):
            wa = xa[w:w + 4]; wb = xb[w:w + 4]; words += 1
            if wa == wb: continue
            word_bad += 1
            r = rel(fl(wa.hex()), fl(wb.hex()))
            for name, lim in BUCKETS[1:]:
                if r <= lim:
                    dist[name] += 1; break
            if first is None: first = ("blk", k, w, wa.hex(), wb.hex())
print(f"groups={n_grp} group_count_differs={cnt_diff_n} coef_calls={n_rec}")
print("input mismatch (calls): " + " ".join(f"{f}={in_bad[f]}" for f in ("ty", "o2", "f", "q", "g", "sr")))
print(f"blk mismatch calls={blk_bad_rec} / {n_rec}; mismatched float words={word_bad} / {words}")
print("rel dist of mismatched words (|SC-KH|/|KH|): " + " ".join(f"{n}={dist[n]}" for n, _ in BUCKETS[1:]))
print(f"first mismatch: {first}")
