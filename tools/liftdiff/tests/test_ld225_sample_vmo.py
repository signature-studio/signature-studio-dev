"""LD-225 (#4561): sample:N の集合に OBJ_PATTERNS の VA (691dd0) を含める規則の単体テスト。
失敗で非 0 終了。規則 (liftdiff.sample_vas の OBJ_PATTERNS 合併) を外すと、この test が落ちる。"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from ldlib import cases  # noqa: E402
import liftdiff  # noqa: E402

VA = 0x691dd0


def main():
    allv = sorted({VA} | {0x100000 + i * 0x10 for i in range(7420)})
    assert len(allv) == 7421 and VA in allv
    bare = sorted(random.Random(1).sample(allv, 800))
    assert VA not in bare, 'precondition: 691dd0 は Random(1) の素の抽出に入らない'
    assert VA in cases.OBJ_PATTERNS, cases.OBJ_PATTERNS
    got = liftdiff.sample_vas(allv, 800)
    assert VA in got, 'sample:800 に 691dd0 が入る'
    assert len(got) == 801, len(got)
    assert set(bare) <= set(got), '素の抽出 800 件は変わらない'
    assert got == sorted(got)
    print('PASS test_ld225_sample_vmo')


if __name__ == '__main__':
    main()
