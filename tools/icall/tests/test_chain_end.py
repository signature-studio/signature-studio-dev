#!/usr/bin/env python3
"""prep_targets.chain_end の境界条件 (PE 不要)。python3 tests/test_chain_end.py"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import prep_targets as P

fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(info) if info and not cond else ''))
    if not cond:
        fails.append(name)


class Img:
    def __init__(self, pdata, chained, bounds):
        self.pdata = pdata
        self.pdata_chained = set(chained)
        self.bounds = sorted(bounds)
        self.pdata_starts = sorted(pdata)


# 親 0x100-0x180, 断片 0x180-0x1c0 (親 0x100), 断片 0x1c0-0x200 (親 0x100) -> 0x200 まで伸びる
img = Img({0x100: 0x180, 0x180: 0x1c0, 0x1c0: 0x200}, [0x180, 0x1c0], [0x100, 0x180, 0x1c0, 0x200])
par = {0x180: 0x100, 0x1c0: 0x100}
check('chain 先が一致 -> 末尾まで伸ばす', P.chain_end(img, 0x100, 0x180, par) == 0x200, hex(P.chain_end(img, 0x100, 0x180, par)))

# 断片の親が別関数 (0x100 とは別の 0x0f0 の cold) -> 伸ばさない
par2 = {0x180: 0x0f0, 0x1c0: 0x0f0}
check('親が別関数 -> 伸ばさない', P.chain_end(img, 0x100, 0x180, par2) == 0x180)

# 途中に他関数の開始 VA (0x1a0) がある -> 伸ばさない
img2 = Img({0x100: 0x180, 0x180: 0x1c0, 0x1c0: 0x200}, [0x180, 0x1c0], [0x100, 0x180, 0x1a0, 0x1c0, 0x200])
check('他関数の開始 VA を跨ぐ -> 伸ばさない', P.chain_end(img2, 0x100, 0x180, par) == 0x180)

# 連鎖していない (pdata_chained に無い) -> 変えない
img3 = Img({0x100: 0x180, 0x180: 0x1c0}, [], [0x100, 0x180])
check('未連鎖 -> 変えない', P.chain_end(img3, 0x100, 0x180, {}) == 0x180)

print('FAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)
