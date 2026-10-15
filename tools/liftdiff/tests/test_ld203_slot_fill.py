"""LD-203 (#4200): 653c80 の間接 call slot (image RVA 0x11f3480) を boot 状態で仮 proc に埋める case 行の単体テスト。
失敗で非 0 終了。規則 (PATCH_BY_VA) を外すと、この test が落ちる。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from ldlib import cases  # noqa: E402

SIG = {'ret': 'i64', 'params': ['i64', 'i64', 'i128'], 'defined': True}
SLOT_PATCH = 'i:0x11f3480:q=0x50012000'


def main():
    assert cases.PATCH_BY_VA[0x653c80] == SLOT_PATCH, cases.PATCH_BY_VA
    s = cases.machine_sig(0x653c80, SIG)
    line = cases.case_line(0x653c80, 'function_653c80', 'z', s)
    assert ' p=' + SLOT_PATCH in line, line
    other = cases.case_line(0x691dd0, 'function_691dd0', 'z', cases.machine_sig(0x691dd0, SIG))
    assert ' p=' not in other, other
    print('PASS test_ld203_slot_fill')


if __name__ == '__main__':
    main()
