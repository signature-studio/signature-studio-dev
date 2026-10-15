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
for c in range(N):
    b = bytearray(base)
    if c > 0:
        for _ in range(rng.randrange(1, 9)):
            b[rng.randrange(sz)] = rng.randrange(256)
    out.append(bytes(b))
open(f"{W}/cases.bin", "wb").write(b"".join(out))
print(f"[wc_cases] cases={N} data_sz=0x{sz:x} (case 0 = original .data)")
