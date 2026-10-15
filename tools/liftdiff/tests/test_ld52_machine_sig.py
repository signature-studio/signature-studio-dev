"""LD-52 (#1528): 機械語入口型の投入 (cases.machine_sig・case_line・fvm_line の wsig/tr) の単体テスト。失敗で非 0 終了。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import cases  # noqa: E402

IR_SIG = {'ret': 'i64', 'params': ['i128'], 'defined': True}


def main():
    assert not cases.supported_sig(IR_SIG)
    for va in cases.MACHINE_ENTRY:
        s = cases.machine_sig(va, IR_SIG)
        assert cases.supported_sig(s), hex(va)
        assert s['tr'] is True and s['wsig'] == ['i64'] * len(s['params']), hex(va)
    assert cases.machine_sig(0x1234, IR_SIG) is IR_SIG
    s = cases.machine_sig(0x40c660, IR_SIG)
    assert s['params'] == ['double'] and s['ret'] == 'i64'
    line = cases.case_line(0x40c660, 'function_40c660', 'z', s)
    assert ' tr=1 ' in line + ' ' and ' wsig=i64 ' in line + ' ' and ' sig=double ' in line + ' ', line
    assert ' args=d:0x3ff8000000000000,' in line, line
    plain = cases.case_line(0x1234, 'function_1234', 'z', {'ret': 'i64', 'params': ['i64'], 'defined': True})
    assert 'wsig=' not in plain and 'tr=1' not in plain, plain
    fv = cases.fvm_line(0x653c80, 'function_653c80', 2, cases.machine_sig(0x653c80, IR_SIG))
    assert 'wsig=i64,i64,i64' in fv and 'tr=1' in fv, fv
    print('PASS test_ld52_machine_sig')


if __name__ == '__main__':
    main()
