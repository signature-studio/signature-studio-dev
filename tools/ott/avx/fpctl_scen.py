#!/usr/bin/env python3
"""fpctl_scen.py — CAB-135: FP 制御切替関数 0x1801bc890 (powf 系, __use_fma3 分岐 +
stmxcsr/ldmxcsr + rcr) を virt step で直接叩く unit scenario 群。

0x1801bc890 は通常 coverage では入口 + flag 分岐のみ実行 (mxcsr dance / rcr は入力依存で未達)。
(x, y) を揃えて (a) mxcsr dance 経路 (x<0, |y|<2^23, y 整数/非整数) (b) rcr parity 両側
(c) x==0 / |y|>=2^23 の skip 経路 (d) FMA 強制時の VEX 版 (0x1801bcff6..) を実行させる。

usage: fpctl_scen.py OUT.json   → avx_matrix.py で --force '' / --force fma,isa の両方で突合
"""
import json
import sys

FPCTL = 0x1bc890

# (x, y): powf 風 2 float 引数。xmm0=x, xmm1=y
CASES = [
    ('neg_int_even', -2.0, 4.0),      # mxcsr dance → y→4 (偶数) → rcr CF=0 → jae
    ('neg_int_odd', -2.0, 3.0),       # dance → y→3 (奇数) → rcr CF=1 → movss 定数
    ('neg_frac', -2.0, 3.5),          # dance → y 非整数 → ucomiss jne → 0x1801bcfd0
    ('neg_bigy', -2.0, 1e30),         # |y|>=2^23 → dance skip
    ('pos', 2.0, 4.0),                # x>0 (bit pattern) → dance skip
    ('zero_x', -0.0, 2.0),            # x==0 → 0x1801bcb30 側 (第2 rcr 0x1801bcb9e)
    ('zero_x_frac', -0.0, 2.5),       # 同上 + 非整数 y
    ('neg_frac_y2', -8.0, -0.25),     # 負 y → 1/x 系
    ('neg_big', -1e30, 2.0),          # |x| 大, dance あり
    ('neg_tiny', -1e-30, 2.0),        # denormal 近傍
]


def main():
    S = []
    for name, x, y in CASES:
        S.append({'name': 'fpctl_' + name,
                  'steps': [{'c': 'virt', 'rva': FPCTL, 'xmm': {0: x, 1: y}}]})
    json.dump(S, open(sys.argv[1], 'w'), indent=1)
    print('[fpctl_scen] scenarios %d -> %s' % (len(S), sys.argv[1]))


if __name__ == '__main__':
    main()
