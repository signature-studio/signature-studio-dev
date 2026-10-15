#!/usr/bin/env python3
"""ks_vf_state_cmp.py <sc.txt> <kh.txt> — VocalFilter の state 比較 (#4417 / FA-54)。
窓は機械語の読みで確定した対応 (REPORT_APPENDIX_FA51.md §7.1):
  DF2 状態 (f64 ペア 組 0..7・16 B × 8 = 0x80 B): SC S+0xa0 ↔ KH this+0x70。
  sr: SC S+0x98 ↔ KH this+0x60。
  ctx の 0x668..0x670 (SC は S+0x12d8 側の合算バッファのポインタ・KH は this+0x12d8) はハーネスのアドレスなので
  状態として比べない。ポインタの値以外の ctx 領域 (0x668 B) は比べる。
判定は C5 (bit 一致・ulp 許容 0)。f64 の差は組ごとに max |SC-KH|/|KH| を書く。
出力: 領域ごとの bit 不一致 call 数、組ごとの差 call 数と最大相対差。"""
import struct
import sys

SC_SR, KH_SR = 0x98, 0x60
SC_DF2, KH_DF2 = 0xa0, 0x70
DF2_BYTES = 0x80
PTR_OFF = 0x668
CTX_BYTES = 0x670


def parse(path):
    rows = []
    for line in open(path).read().splitlines():
        parts = line.split(" |")
        for seg in parts[1:]:
            # seg: sr(8 B) + arr1(0x200 B) + arr2(0x200 B) + ctx(0x670 B) + " " L " " R
            sr = bytes.fromhex(seg[0:16])
            arr1 = bytes.fromhex(seg[16:16 + 0x400])
            arr2 = bytes.fromhex(seg[16 + 0x400:16 + 0x800])
            ctx = bytes.fromhex(seg[16 + 0x800:16 + 0x800 + 2 * CTX_BYTES])
            rows.append((sr, arr1, arr2, ctx))
    return rows


def main():
    sc = parse(sys.argv[1])
    kh = parse(sys.argv[2])
    assert len(sc) == len(kh), (len(sc), len(kh))
    n = len(sc)
    sr_bad = sum(1 for a, b in zip(sc, kh) if a[0] != b[0])
    df2_bad = sum(1 for a, b in zip(sc, kh) if a[1][:DF2_BYTES] != b[1][:DF2_BYTES])
    ctx_bad = sum(1 for a, b in zip(sc, kh) if a[3][:PTR_OFF] != b[3][:PTR_OFF])
    ctx_ptr_only = sum(1 for a, b in zip(sc, kh) if a[3][PTR_OFF:CTX_BYTES] != b[3][PTR_OFF:CTX_BYTES])
    print(f"calls={n}")
    print(f"sr        S+0x98/KH+0x60        bit mismatch calls={sr_bad}")
    print(f"DF2 f64x16 S+0xa0/KH+0x70 (0x80 B) bit mismatch calls={df2_bad}")
    print(f"ctx 0x000..0x668 (excl. pointer)  bit mismatch calls={ctx_bad}")
    print(f"ctx 0x668..0x670 (pointer field)  mismatch calls={ctx_ptr_only} (harness address, not state)")
    print("per DF2 pair (f64): calls with diff / max |SC-KH|/|KH|")
    for i in range(DF2_BYTES // 16):
        dc, mx = 0, 0.0
        for a, b in zip(sc, kh):
            sv = struct.unpack("<dd", a[1][16 * i:16 * i + 16])
            kv = struct.unpack("<dd", b[1][16 * i:16 * i + 16])
            if sv != kv:
                dc += 1
                for x, y in zip(sv, kv):
                    if y != 0.0 and x != y:
                        mx = max(mx, abs(x - y) / abs(y))
        print(f"  pair {i} (S+0x{SC_DF2 + 16 * i:x} / this+0x{KH_DF2 + 16 * i:x}): calls={dc} max_rel={mx:.3e}")


if __name__ == "__main__":
    main()
