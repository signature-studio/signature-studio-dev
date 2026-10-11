#!/usr/bin/env python3
"""acc_qebig_probe.py — qebig vectors の中身を確認: 各 call の入力 x, native 戻り (xmm0), rk。

usage: acc_qebig_probe.py <qebig.bin> [n]
"""
import math
import struct
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from acc_khvec import Vec  # noqa: E402


def f64(u):
    return struct.unpack('<d', struct.pack('<Q', u))[0]


def main():
    p = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    v = Vec(p)
    shown = 0
    for t in v.trials:
        for c in t:
            x = f64(c['x'][0])
            r = f64(c['xmm0'])
            print('va=%s  rk=%d  x=%.17g  ret=%.17g   ulp(x)=%.3g' %
                  (hex(c['va']), c['rk'], x, r, math.ulp(x)))
            shown += 1
            if shown >= n:
                return


if __name__ == '__main__':
    main()
