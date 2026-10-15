#!/usr/bin/env python3
"""PY-230 (#3669): 空の pattern 1 の L (行 +0x50) の既定値を、PE の静的な値の連鎖から計算する (解析補助。実行の確認ではない)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py230_l_default.py [--expect-n <整数>]

連鎖 (REPORT_PY225.md の PY-230 節):
  空の行 → 0x12d19bd: r13 = 0x1062840([rbp+0x54]) = byte[p] * f * V
    p = 既定の拍子 {N, D} (0x1062930 の既定値 → 0x1062890 が N = byte [*(0x15e39c0)]、D = 16 / C)
    f = 0x10627f0: flag byte [*(0x15e37c8)] == 1 なら 16 / D、そうでなければ C = [*(0x15e1c70)]
    V = [*(0x15e25f8)] (ticks per step)
  空の項目リスト (0x1062c50 が -1) で [行+0x44] = 0 のとき: L = max([行+0x48], r13) (0x12d1b2e)。[行+0x48] = 0 を仮定
  n = ceil(L / X) * C (0x12d09e0)。X = [*(0x15e27f0)] (PPQ)。

この式は静的な値だけで計算する。実行時の順序・callback (行 +0x20) の既定値・フラグの実行時の値は未確認 (REPORT_PY225.md の未解決)。
--expect-n を与えると、n がその値と一致しないとき rc 1 で終わる (ネガティブコントロール: 64 は一致しない)。
"""
import os
import struct
import sys

import pefile

DIR = os.environ["FL_WIN64_DIR"]
PE = os.path.join(DIR, "extracted", "block00031_PE.bin")


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    return raw, pe, base


def read(img, va, size):
    raw, pe, base = img
    for s in pe.sections:
        lo = base + s.VirtualAddress
        if lo <= va and va + size <= lo + s.SizeOfRawData:
            off = s.PointerToRawData + (va - lo)
            return raw[off:off + size]
    raise SystemExit("not in file: 0x%x" % va)


def u8(img, va):
    return read(img, va, 1)[0]


def u32(img, va):
    return struct.unpack("<I", read(img, va, 4))[0]


def ptr(img, va):
    return struct.unpack("<Q", read(img, va, 8))[0]


def main():
    expect = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--expect-n":
        expect = int(sys.argv[2])
    img = load()
    N = u8(img, ptr(img, 0x15E39C0))
    C = u32(img, ptr(img, 0x15E1C70))
    V = u32(img, ptr(img, 0x15E25F8))
    X = u32(img, ptr(img, 0x15E27F0))
    flag = u8(img, ptr(img, 0x15E37C8))
    D = 16 // C
    f = 16 // D if flag == 1 else C
    r13 = N * f * V
    L = max(0, r13)
    n = ((L + X - 1) // X) * C
    print("N (既定の拍子の分子, [*(0x15e39c0)])   = %d" % N)
    print("C (1 拍の step 数, [*(0x15e1c70)])     = %d" % C)
    print("D (既定の拍子の分母, 16 / C)            = %d" % D)
    print("flag (byte [*(0x15e37c8)])              = %d" % flag)
    print("f (0x10627f0: flag==1 ? 16/D : C)       = %d" % f)
    print("V (ticks per step, [*(0x15e25f8)])      = %d" % V)
    print("X (PPQ, [*(0x15e27f0)])                  = %d" % X)
    print("r13 = N*f*V (1 小節の ticks)            = %d" % r13)
    print("L = max([行+0x48]=0, r13)               = %d" % L)
    print("n = ceil(L/X)*C                          = %d" % n)
    if expect is not None:
        ok = n == expect
        print("expect n=%d: %s" % (expect, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
