#!/usr/bin/env python3
"""ks_semantic_gain の SC/KH 不一致 case を ulp 距離で分類する。
   usage: ks_semantic_gain_ulp.py <sc.txt> <kh.txt>
 case ごとに L/R 出力の最大 ulp 差 (float32 の符号付き整数表現の差) を求め、
 ulp 距離のヒストグラムを 1 行の JSON で出す。ulp >= 10 は 10 にまとめる。
 符号が違う (ulp 距離が 2^31 級) case は sign_flip として別計上する。
"""
import json, struct, sys
from collections import Counter


def parse(path):
    rows = {}
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t or not t[0].startswith("C"):
                continue
            kv = dict(x.split("=") for x in t[1:6])
            rows[int(t[0][1:])] = (kv, t[8], t[9])
    return rows


def floats(h):
    if h == "-":
        return []
    return list(struct.unpack("<%df" % (len(h) // 8), bytes.fromhex(h)))


def ordinal(x):
    i = struct.unpack("<i", struct.pack("<f", x))[0]
    return i if i >= 0 else -(i & 0x7FFFFFFF)


def main():
    sc, kh = parse(sys.argv[1]), parse(sys.argv[2])
    hist = Counter()
    sign_flip = 0
    for k in sorted(set(sc) & set(kh)):
        _, L1, R1 = sc[k]
        _, L2, R2 = kh[k]
        if L1 == L2 and R1 == R2:
            continue
        mx = 0
        flip = False
        for x, y in zip(floats(L1) + floats(R1), floats(L2) + floats(R2)):
            if x != x or y != y:
                continue
            if (x < 0) != (y < 0) and x != 0 and y != 0:
                flip = True
            mx = max(mx, abs(ordinal(x) - ordinal(y)))
        if flip:
            sign_flip += 1
        hist[min(mx, 10)] += 1
    print(json.dumps({"mismatch_cases": sum(hist.values()),
                      "max_ulp_hist": {str(k): hist[k] for k in sorted(hist)},
                      "sign_flip_cases": sign_flip}, ensure_ascii=False))


if __name__ == "__main__":
    main()
