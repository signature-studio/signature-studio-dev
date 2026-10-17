#!/usr/bin/env python3
# test_value_judge_6124.py: value_judge_6124.judge の規則確認 (#6124 ネガコン)。
# 規則を壊すと (例: 観測欠落を一致扱いにする・候補複数を順序で決める) このテストが落ちる。
# 実行: python3 tools/m11/ldfix/test_value_judge_6124.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_judge_6124 import judge

G = [{'k': 'K1', 'blk': 'B1', 'ir': [0, 1], 'mach': [0, 1]}]


def rows(ir, mach):
    out = []
    for h, (a, b) in enumerate(zip(ir, mach)):
        out.append({'side': 'ir', 'k': 'K1', 'blk': 'B1', 'idx': 0, 'hit': h, 'value': a[0]})
        out.append({'side': 'ir', 'k': 'K1', 'blk': 'B1', 'idx': 1, 'hit': h, 'value': a[1]})
        out.append({'side': 'mach', 'k': 'K1', 'blk': 'B1', 'idx': 0, 'hit': h, 'value': b[0]})
        out.append({'side': 'mach', 'k': 'K1', 'blk': 'B1', 'idx': 1, 'hit': h, 'value': b[1]})
    return out


def verdict(r, g=G):
    return judge(g, r)[0]['verdict']


def main():
    # 正: 全 hit で値が 1 対 1 に一致する (IR 0↔chain 0, IR 1↔chain 1)
    assert verdict(rows([(1, 2), (3, 4)], [(1, 2), (3, 4)])) == '一致'
    # ネガ 1: 値が一致しない (IR 0 と chain 0 が 1 hit で食い違う) → 一致扱いにしない
    assert verdict(rows([(1, 2), (3, 4)], [(9, 2), (3, 4)])) == '不一致'
    # ネガ 2: 観測欠落 (chain 1 の hit 1 が無い) → 判定不能 (一致にしない)
    r = rows([(1, 2), (3, 4)], [(1, 2), (3, 4)])
    r = [x for x in r if not (x['side'] == 'mach' and x['idx'] == 1 and x['hit'] == 1)]
    assert verdict(r) == '判定不能'
    # ネガ 3: 観測 0 件 → 判定不能
    assert verdict([]) == '判定不能'
    # ネガ 4: 候補が複数 (IR 0 と IR 1 の値が全 hit で同じ) → 順序で決めず判定不能
    assert verdict(rows([(5, 5), (6, 6)], [(5, 5), (6, 6)])) == '判定不能'
    print('test_value_judge_6124: OK (5 cases)')


if __name__ == '__main__':
    main()
