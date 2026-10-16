#!/usr/bin/env python3
"""PY-4909 (#5313) G6 0x104bffa: [rbp+0x580] の符号付き /8 (0x104be56〜0x104be66) と [rbp+0x568] の符号付き %8 (0x104bd33〜0x104bd49) の分岐を、
C の trunc 除算・剰余と全入力で突合する (実機不要)。

  python3 analysis/py64_sign_branch_check.py

- 手計算の式は ⚠合流 を含むため py64_check_expr.py の HAND 表には入らない。ここでは分岐の意味だけを検証する。
- 入力: v = (and(c_in,0xffff) + 0x70000000 − 0x70001fd0) を 32bit の符号付きで、c_in の下位 16bit の全 65536 通り + 乱数 20000。
- 合格なら exit 0。
"""
import random


def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def c_div8(v):
    return int(v / 8) if v >= 0 else -((-v) // 8)


def c_mod8(v):
    return v - 8 * c_div8(v)


def asm_div8(v):  # 0x104be56: test eax,eax / jns / add eax,7 / sar eax,3
    e = s32(v)
    if e < 0:
        e = s32(e + 7)
    return e >> 3


def asm_mod8(v):  # 0x104bd33: and eax,0x80000007 / jns / sub 1 / or 0xfffffff8 / add 1
    a = s32(v & 0x80000007)
    if a >= 0:
        return a
    return s32(s32(((a - 1) & 0xFFFFFFFF) | 0xFFFFFFF8) + 1)


def main():
    vals = [(c - 0x1FD0) for c in range(65536)]
    vals += [s32(random.randrange(1 << 32)) for _ in range(20000)]
    bad_div = sum(asm_div8(v) != c_div8(v) for v in vals)
    bad_mod = sum(asm_mod8(v) != c_mod8(v) for v in vals)
    print(f"# n={len(vals)} div8 mismatch={bad_div} mod8 mismatch={bad_mod}")
    raise SystemExit(1 if bad_div or bad_mod else 0)


if __name__ == "__main__":
    main()
