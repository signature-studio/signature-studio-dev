"""LD-207 (#4264): 691dd0 に vtable 付き有効オブジェクト (vmo pattern) を足す規則の単体テスト。
失敗で非 0 終了。規則 (OBJ_PATTERNS) を外すと、この test が落ちる。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from ldlib import cases  # noqa: E402

SIG = {'ret': 'i64', 'params': ['i64', 'i128', 'i64'], 'defined': True}


def main():
    assert cases.OBJ_PATTERNS.get(0x691dd0), cases.OBJ_PATTERNS
    assert [p[0] for p in cases.OBJ_PATTERNS[0x691dd0]] == ['vmo'], cases.OBJ_PATTERNS
    assert 'vmo' not in cases.PATTERN_NAMES, cases.PATTERN_NAMES
    toks, blob = cases.build_args('vmo', ['i', 'i', 'i'])
    assert blob == 'vmt' and toks == ['i:a:0x%x' % cases.PTR_SLOTS[0], 'i:0x0', 'i:0x0'], (toks, blob)
    s = cases.machine_sig(0x691dd0, SIG)
    line = cases.case_line(0x691dd0, 'function_691dd0', 'vmo', s)
    assert ' blob=vmt ' in line and 'i:a:0x1000' in line, line
    other = cases.OBJ_PATTERNS.get(0x653c80)
    assert other is None, other
    print('PASS test_ld207_obj_pattern')


if __name__ == '__main__':
    main()
