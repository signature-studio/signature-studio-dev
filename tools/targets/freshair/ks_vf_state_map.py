#!/usr/bin/env python3
"""ks_vf_state_map.py <sc.txt> <kh.txt> — arr 領域 (SC S+0xa0 / KH this+0x70・0x200 B = 16 B 組 32 個) の組対応を実測で確認する (#4417 / FA-54)。

組 i (16 B = f64 ペア) ごとに、SC 組 i と KH 組 j が call ごとに bit 一致した回数を数える。
対角 (i==j) が 600 なら位置は同じ。対角が小さく、別の j と一致するなら写像のずれ。
hex 比較と struct の f64 比較を両方出す (独立な検算)。"""
import struct
import sys

SC_OFF = 0xa0
KH_OFF = 0x70
PAIR_B = 16
PAIRS = 0x200 // PAIR_B


def parse(path):
    rows = []
    for line in open(path).read().splitlines():
        parts = line.split(" |")
        body = parts[1:]
        calls = []
        for seg in body:
            # seg = sr(8B hex) + arr1(0x200 B hex) + arr2(0x200 B hex) + ctx(0x670 B hex) + " " L " " R
            sr_hex = seg[0:16]
            arr1 = seg[16:16 + 0x400]
            calls.append((sr_hex, arr1))
        rows.append(calls)
    return rows


def pair_bytes(arr1_hex, off_in_arr, i):
    b = off_in_arr + i * PAIR_B
    return bytes.fromhex(arr1_hex[2 * b:2 * (b + PAIR_B)])


def main():
    sc = parse(sys.argv[1])
    kh = parse(sys.argv[2])
    assert len(sc) == len(kh)
    # arr1 は S+0xa0 (SC) / this+0x70 (KH) から 0x200 B。組 i は arr1 先頭からの 16i B。
    match = [[0] * PAIRS for _ in range(PAIRS)]
    fmatch = [[0] * PAIRS for _ in range(PAIRS)]
    ncall = 0
    for sline, kline in zip(sc, kh):
        for (_, sa), (_, ka) in zip(sline, kline):
            ncall += 1
            for i in range(PAIRS):
                si = pair_bytes(sa, 0, i)
                for j in range(PAIRS):
                    kj = pair_bytes(ka, 0, j)
                    if si == kj:
                        match[i][j] += 1
                    sv = struct.unpack("<dd", si)
                    kv = struct.unpack("<dd", kj)
                    if all(a == b for a, b in zip(sv, kv)):
                        fmatch[i][j] += 1
    win = 8 * PAIR_B
    win_eq = 0
    for sline, kline in zip(sc, kh):
        for (_, sa), (_, ka) in zip(sline, kline):
            if sa[:2 * win] == ka[:2 * win]:
                win_eq += 1
    print(f"window SC S+0x{SC_OFF:x}..+0x{SC_OFF + win:x} vs KH this+0x{KH_OFF:x}..+0x{KH_OFF + win:x} ({win} B): bit-equal calls={win_eq}/{ncall}")
    print(f"calls={ncall} pairs={PAIRS} pair_bytes={PAIR_B}")
    print("diff pairs (SC i vs KH i): calls with f64 diff / max |SC-KH|/|KH| / first (scen,call)")
    for i in range(PAIRS):
        dc, mx, first = 0, 0.0, None
        for s_idx, (sline, kline) in enumerate(zip(sc, kh)):
            for c_idx, ((_, sa), (_, ka)) in enumerate(zip(sline, kline)):
                sv = struct.unpack("<dd", pair_bytes(sa, 0, i))
                kv = struct.unpack("<dd", pair_bytes(ka, 0, i))
                if sv != kv:
                    dc += 1
                    if first is None:
                        first = (s_idx, c_idx)
                    for a, b in zip(sv, kv):
                        if b != 0.0:
                            mx = max(mx, abs(a - b) / abs(b))
        if dc:
            print(f"  i={i:2d} calls={dc:4d} max_rel={mx:.3e} first={first}")
    print("diagonal (SC pair i vs KH pair i, bit-exact count of calls):")
    for i in range(PAIRS):
        best = max(range(PAIRS), key=lambda j: match[i][j])
        print(f"  i={i:2d} S+0x{SC_OFF + PAIR_B * i:03x} diag={match[i][i]:4d} best_j={best:2d} best_count={match[i][best]:4d} "
              f"| f64 diag={fmatch[i][i]:4d}")


if __name__ == "__main__":
    main()
