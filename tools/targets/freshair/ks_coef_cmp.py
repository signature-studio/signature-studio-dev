#!/usr/bin/env python3
"""ks_coef_cmp.py <sc_coef.txt> <kh_coef.txt> — 係数計算関数 (SC 0x180b7fa80 / KH 0x180469d40) の呼出し引数と入口・出口の係数ブロックを両側で比べる。
入力は lift2/native/coef_probe.c の出力 ("P <sidx> <call>" で処理 call を区切り、"I blk=<hex>" が係数計算の入口ブロック、
"E ty= o2= f= q= g= sr= blk=<hex>" が係数計算 1 回の出口)。
判定に使う集計: 入力 (ty/o2/f/q/g/sr) の bit 一致、入口ブロックの bit 一致、出口ブロック (float32 語) の bit 一致と相対差
|SC−KH|/|KH| の分布、入口一致/不一致 × 出口一致/不一致 の 2×2 表、o2 別の出口不一致、最初に不一致になった語。"""
import math
import struct
import sys
from collections import Counter, defaultdict

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
            i = len(groups[key])
            d["pre"] = pre[key][i] if i < len(pre.get(key, [])) else ""
            groups[key].append(d)
    return groups

def fl(h): return struct.unpack("<f", bytes.fromhex(h))[0]

def rel(a, b):
    if math.isnan(a) or math.isnan(b): return math.inf
    if b == 0.0: return 0.0 if a == 0.0 else math.inf
    return abs(a - b) / abs(b)

BUCKETS = [("<=1e-6", 1e-6), ("<=1e-4", 1e-4), ("<=1e-3", 1e-3), ("<=1e-2", 1e-2), (">1e-2", math.inf)]
FIELDS = ("ty", "o2", "f", "q", "g", "sr")

sc = parse(sys.argv[1]); kh = parse(sys.argv[2])
keys = sorted(set(sc) | set(kh))
n_grp = len(keys); cnt_diff_n = 0; n_rec = 0; in_bad = Counter(); blk_bad_rec = 0
pre_bad_rec = 0; words = 0; word_bad = 0; dist = Counter(); first = None
tbl = Counter()                 # (入口一致?, 出口一致?) -> call 数
o2_tot = Counter(); o2_bad = Counter()
word_off_bad = Counter()        # 不一致語の位置 (word index) の出現数
big_kh = Counter()              # |KH| > 0 の 1e-2 超の語を |KH| の大きさで区分
for k in keys:
    a = sc.get(k, []); b = kh.get(k, [])
    if len(a) != len(b):
        cnt_diff_n += 1
        if first is None: first = ("count", k, len(a), len(b))
    for ra, rb in zip(a, b):
        n_rec += 1
        for f in FIELDS:
            if ra.get(f) != rb.get(f):
                in_bad[f] += 1
                if first is None: first = ("input", k, f, ra.get(f), rb.get(f))
        pre_same = ra["pre"] == rb["pre"]
        if not pre_same:
            pre_bad_rec += 1
            if first is None: first = ("pre", k, ra["pre"][:16], rb["pre"][:16])
        o2 = ra.get("o2", "?"); o2_tot[o2] += 1
        xa = bytes.fromhex(ra["blk"]); xb = bytes.fromhex(rb["blk"])
        out_same = xa == xb
        tbl[(pre_same, out_same)] += 1
        if out_same: continue
        blk_bad_rec += 1; o2_bad[o2] += 1
        for w in range(0, min(len(xa), len(xb)), 4):
            wa = xa[w:w + 4]; wb = xb[w:w + 4]; words += 1
            if wa == wb: continue
            word_bad += 1; word_off_bad[w] += 1
            va = fl(wa.hex()); vb = fl(wb.hex()); r = rel(va, vb)
            for name, lim in BUCKETS:
                if r <= lim:
                    dist[name] += 1; break
            if r > 1e-2 and not math.isnan(vb):
                if abs(vb) < 1e-20: big_kh["|KH|<1e-20"] += 1
                elif abs(vb) < 1e-3: big_kh["1e-20<=|KH|<1e-3"] += 1
                else: big_kh["|KH|>=1e-3"] += 1
            if first is None: first = ("out", k, w, wa.hex(), wb.hex())

print(f"groups={n_grp} group_count_differs={cnt_diff_n} coef_calls={n_rec}")
print("input mismatch (calls): " + " ".join(f"{f}={in_bad[f]}" for f in FIELDS))
print(f"entry block (pre) mismatch calls={pre_bad_rec} / {n_rec}")
print(f"out block mismatch calls={blk_bad_rec} / {n_rec}; mismatched float words={word_bad} / {words}")
print("2x2 (entry same/diff x out same/diff): "
      f"entry_same&out_same={tbl[(True, True)]} entry_same&out_diff={tbl[(True, False)]} "
      f"entry_diff&out_same={tbl[(False, True)]} entry_diff&out_diff={tbl[(False, False)]}")
print("out mismatch by o2: " + " ".join(f"o2={o}:{o2_bad[o]}/{o2_tot[o]}" for o in sorted(o2_tot)))
print("rel dist of mismatched words (|SC-KH|/|KH|): " + " ".join(f"{n}={dist[n]}" for n, _ in BUCKETS))
print("|KH| of mismatched words with rel>1e-2: " + " ".join(f"{n}={big_kh[n]}" for n in ("|KH|<1e-20", "1e-20<=|KH|<1e-3", "|KH|>=1e-3")))
print("first mismatched word byte offsets (offset:count): " + " ".join(f"0x{w:x}:{c}" for w, c in sorted(word_off_bad.items())[:12]))
print(f"first mismatch: {first}")
