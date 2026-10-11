#!/usr/bin/env python3
"""acc_qebig_semantics.py — k_dfdb0 / sincos_a の戻り値の意味を独立に推定 (高精度 Decimal で)。

目的 (規則 40): wasm が native と一致しても、native 参照自体が「意味のある値」を返していることを
確認する (junk 同士の一致ではない)。別アルゴリズム = Python decimal の多倍長 π による
Payne-Hanek 風還元 (C 実装とは別実装)。

仮説:
  sincos_a(x) = sin(x)                    (MSVC sincos の sin 側)
  k_dfdb0(x)  = Payne-Hanek 還元値 r        (x mod M のある形, M = pi/2 or pi)
判定は |r - r_ref| <= 4*ulp(x) (還元誤差は O(x*2^-53) に比例するため)
"""
import struct
import sys
from decimal import Decimal, getcontext

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from acc_khvec import Vec  # noqa: E402

getcontext().prec = 200


def f64(u):
    return struct.unpack('<d', struct.pack('<Q', u))[0]


def ulp(x):
    if x == 0:
        return 5e-324
    import math
    return math.ulp(x)


def pi_hi(n):
    """pi の n 桁 (Decimal)"""
    getcontext().prec += 10
    # Chudnovsky ではなく Machin 公式で十分 (prec=200)
    def arctan_inv(x):
        x = Decimal(x)
        total = Decimal(0)
        term = Decimal(1) / x
        x2 = Decimal(1) / (x * x)
        k = 0
        while True:
            t = term / (2 * k + 1)
            if t == 0:
                break
            total += t if k % 2 == 0 else -t
            term *= x2
            k += 1
            if k > 400:
                break
        return total
    p = 16 * arctan_inv(5) - 4 * arctan_inv(239)
    getcontext().prec -= 10
    return +p


PI = pi_hi(2)


def ref_reduce(x, modulus):
    """x mod modulus (Decimal) を [-modulus/2, modulus/2) に正規化して返す"""
    xd = Decimal(x)
    n = (xd / modulus).to_integral_value(rounding='ROUND_HALF_EVEN')
    r = xd - n * modulus
    return xd, n, r


def main():
    p = sys.argv[1]
    v = Vec(p)
    cnt = {'sincos': 0, 'dfdb0': 0}
    ok = {'sincos': 0, 'dfdb0': 0}
    bad = []
    for t in v.trials:
        for c in t:
            x = f64(c['x'][0])
            r = f64(c['xmm0'])
            which = 'sincos' if c['va'] == 0x180fcd690 else 'dfdb0'
            cnt[which] += 1
            if which == 'sincos':
                import math
                d = abs(r - math.sin(x))
                if d <= 2 * ulp(r) + 1e-300:
                    ok['sincos'] += 1
                elif len(bad) < 3:
                    bad.append(('sincos', x, r, math.sin(x), d, ulp(r)))
            else:
                # k_dfdb0: x mod (pi/2) で最も近い整数 n を使い r を作る
                best = None
                for mod, sign in ((PI / 2, 1), (PI, 1)):
                    xd = Decimal(x)
                    n = (xd / mod).to_integral_value(rounding='ROUND_HALF_EVEN')
                    rr = xd - n * mod
                    if rr > mod / 2:
                        rr -= mod
                    if rr <= -mod / 2:
                        rr += mod
                    for cand in (rr, rr + mod, rr - mod, rr + mod / 2, rr - mod / 2):
                        d = abs(Decimal(repr(r)) - cand)
                        if best is None or d < best[0]:
                            best = (d, mod, n, cand)
                d, mod, n, cand = best
                if d <= 4 * Decimal(ulp(x)):
                    ok['dfdb0'] += 1
                elif len(bad) < 6:
                    bad.append(('dfdb0', x, r, str(cand), str(d), ulp(x)))
    print('calls: sincos=%d dfdb0=%d' % (cnt['sincos'], cnt['dfdb0']))
    print('within tol (sin: <=2 ulp(ret), dfdb0: <=4 ulp(x)): sincos=%d/%d  dfdb0=%d/%d'
          % (ok['sincos'], cnt['sincos'], ok['dfdb0'], cnt['dfdb0']))
    for b in bad:
        print('  OUT', b)


if __name__ == '__main__':
    main()
