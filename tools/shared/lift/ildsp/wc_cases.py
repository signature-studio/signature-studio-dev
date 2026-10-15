#!/usr/bin/env python3
"""WaveformColouring_CreateInstance の差分テスト用の case を作る (T-SH-52 / #3216)。
case = .data の事前状態 (元の .data をランダムに数バイト書き換えたもの)。case 0 は元の .data。
CreateInstance は引数を読まないため、入力のばらつきは .data の事前状態で与える。
usage: wc_cases.py WORKDIR N     (WORKDIR の layout.json と image_native.bin を読み、cases.bin を書く)
cases.bin: u32 N, その後 N 個 × DATA_SZ バイト。
"""
import json, random, struct, sys
W, N = sys.argv[1], int(sys.argv[2])
L = json.load(open(f"{W}/layout.json"))
img = open(f"{W}/image_native.bin", "rb").read()
d0, sz = L["data_rva"], L["data_sz"]
base = img[d0:d0 + sz]
rng = random.Random(0x3216)
out = [struct.pack("<I", N)]
# WC_CASE_MODE=ref (T-SH-115 / #4303): コードが .data を読む先 (textref) の 8 byte 窓だけを書き換える。
# 既定 (random) は従来どおり .data 全体から 1〜8 byte を選ぶ。
mode = __import__("os").environ.get("WC_CASE_MODE", "random")
if mode == "ref":
    meta = json.load(open(f"{W}/lift/lift_meta.json"))
    IMG = 0x180000000
    wins = sorted({a - IMG - d0 for a in meta["textrefs"] if d0 <= a - IMG < d0 + sz})
    wins = [w for w in wins if 0 <= w and w + 8 <= sz]
    print(f"[wc_cases] ref windows={len(wins)}")
for c in range(N):
    b = bytearray(base)
    if c > 0 and mode == "ref":
        for _ in range(rng.randrange(1, 5)):
            w = rng.choice(wins)
            for k in range(8):
                b[w + k] = rng.randrange(256)
    elif c > 0:
        for _ in range(rng.randrange(1, 9)):
            b[rng.randrange(sz)] = rng.randrange(256)
    out.append(bytes(b))
open(f"{W}/cases.bin", "wb").write(b"".join(out))
print(f"[wc_cases] cases={N} data_sz=0x{sz:x} (case 0 = original .data)")
