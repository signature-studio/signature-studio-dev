#!/usr/bin/env python3
"""PY-53 (#1911): ecx の値から 0x1046a30 の分岐先を算出する (逆アセンブル非依存の検算)。

  python3 analysis/py53_ecx_route.py

ecx_dispatch.txt の比較連鎖 (0x104742a〜0x104745f) を 32bit 演算で再現し、
分岐先の VA を返す。値は境界 (0x0, 0xffffffff, 0x10000000 など) を含めて検査する。
"""

M = 0xFFFFFFFF


def s32(v):
    return v - 0x100000000 if v & 0x80000000 else v


def route(ecx):
    v = ecx & M
    if s32(v) > s32(0x40000001):
        t = (v - 0x40000002) & M
        if t == 0:
            return 0x104C64F
        t = (t - 3) & M
        if t == 0:
            return 0x104C919
        t = (t - 0x2FFFFFFB) & M
        return 0x104AA87 if t < 0x10000000 else 0x104CAAE
    if v == 0x40000001:
        return 0x104C4AF
    t = (v - 0x80000000) & M
    if t < 0x70000000:
        return 0x104AA87
    t = (t - 0x80000000) & M
    if t < 0x10000000:
        return 0x1047497
    t = (t - 0x40000000) & M
    return 0x104C2A6 if t == 0 else 0x104CAAE


CASES = [0x0, 0x1, 0xFFFF, 0x10000000, 0x10000001, 0x20000000, 0x40000000,
         0x40000001, 0x40000002, 0x40000003, 0x40000004, 0x40000005, 0x40000006,
         0x6FFFFFFF, 0x70000000, 0x7FFFFFFF, 0x80000000, 0xEFFFFFFF, 0xF0000000,
         0xFFFFFFFF]

if __name__ == "__main__":
    for c in CASES:
        print(f"ecx={c:#010x} -> {route(c):#x}")
