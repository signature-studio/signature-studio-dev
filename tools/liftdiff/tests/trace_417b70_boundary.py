#!/usr/bin/env python3
"""LD-62 (#1767): predict() の商計算 (旧 int(p / cnt) = 浮動小数点 / 新 = 整数の 0 方向切り捨て) を
exact な商 (Fraction で 0 方向に切り捨てた値) と比べる。素材不要 (計算のみ)。

  python3 tools/liftdiff/tests/trace_417b70_boundary.py > tools/liftdiff/results/m11_417b70_div_boundary.md

p = k*cnt + r (r は -1, 0, 1) を入力にする。r = -1 は割り切れない近傍 (旧式の丸め誤りが出る形)。
"""
from fractions import Fraction
import math

CNTS = [(1 << 60) + 1, 1 << 60, (1 << 60) - 1, (1 << 53) + 1]
KS = [1, 2, 3, 5, 7, 16, 1000, 2147483647]
RS = [-1, 0, 1]


def exact_q(p, cnt):
    return math.trunc(Fraction(p, cnt))


def old_q(p, cnt):
    return int(p / cnt)


def new_q(p, cnt):
    a = abs(p) // abs(cnt)
    return -a if (p < 0) != (cnt < 0) else a


def main():
    print('<!-- 自動生成: python3 tools/liftdiff/tests/trace_417b70_boundary.py (LD-62, #1767) -->')
    print('| cnt | 入力 p の数 | 旧式 (float) が exact と違う | 新式 (整数) が exact と違う |')
    print('|---:|---:|---:|---:|')
    tot_old = tot_new = tot_n = 0
    for cnt in CNTS:
        n = bo = bn = 0
        for k in KS:
            for r in RS:
                p = k * cnt + r
                e = exact_q(p, cnt)
                n += 1
                bo += old_q(p, cnt) != e
                bn += new_q(p, cnt) != e
        tot_n += n
        tot_old += bo
        tot_new += bn
        print('| %d | %d | %d | %d |' % (cnt, n, bo, bn))
    print()
    print('合計: %d 件中 旧式 %d 件不一致 / 新式 %d 件不一致' % (tot_n, tot_old, tot_new))


if __name__ == '__main__':
    main()
