"""LD-52 (#1528): 機械語入口型の投入 (cases.machine_sig・case_line・fvm_line の wsig/tr) と、入口引数の比較 (compare.cmp_trace の i128 位置の除外) の単体テスト。失敗で非 0 終了。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import cases, compare  # noqa: E402

IR_SIG = {'ret': 'i64', 'params': ['i128'], 'defined': True}
IR_653 = {'ret': 'i64', 'params': ['i64', 'i64', 'i128'], 'defined': True}
CTX = compare.Ctx(0, [], (0, 1 << 32))


def entry(va, np_, gpr, fp=()):
    return [va, np_] + list(gpr) + ['0'] * (8 - len(gpr)) + list(fp) + ['0'] * (4 - len(fp))


def trace(e):
    return {'trace': [e]}


def main():
    assert not cases.supported_sig(IR_SIG)
    for va in cases.MACHINE_ENTRY:
        s = cases.machine_sig(va, IR_SIG)
        assert cases.supported_sig(s), hex(va)
        assert s['tr'] is True and s['wsig'] == ['i64'] * len(s['params']), hex(va)
    assert cases.machine_sig(0x1234, IR_SIG) is IR_SIG
    s = cases.machine_sig(0x40c660, IR_SIG)
    assert s['params'] == ['double'] and s['ret'] == 'i64' and s['ir_params'] == ['i128']
    line = cases.case_line(0x40c660, 'function_40c660', 'z', s)
    assert ' tr=1 ' in line + ' ' and ' wsig=i64 ' in line + ' ' and ' sig=double ' in line + ' ', line
    assert ' args=d:0x3ff8000000000000,' in line, line
    plain = cases.case_line(0x1234, 'function_1234', 'z', {'ret': 'i64', 'params': ['i64'], 'defined': True})
    assert 'wsig=' not in plain and 'tr=1' not in plain, plain
    fv = cases.fvm_line(0x653c80, 'function_653c80', 2, cases.machine_sig(0x653c80, IR_653))
    assert 'wsig=i64,i64,i64' in fv and 'tr=1' in fv, fv

    # 比較: 機械語入口型の i128 位置 (653c80 の r8) だけを外し、i64 の位置 (rcx・rdx) は比べる
    sigs = {'function_653c80': cases.machine_sig(0x653c80, IR_653)}
    n = trace(entry('653c80', 3, ['11', '22', '33']))
    assert compare.cmp_trace(n, trace(entry('653c80', 3, ['11', '22', '0'])), CTX, sigs) is None
    r = compare.cmp_trace(n, trace(entry('653c80', 3, ['11', '23', '0'])), CTX, sigs)
    assert r and r['kind'] == 'entry_arg' and r['pos'] == 1, r
    r = compare.cmp_trace(n, trace(entry('653c80', 3, ['10', '22', '0'])), CTX, sigs)
    assert r and r['kind'] == 'entry_arg' and r['pos'] == 0, r

    # 40c660 (IR i128 が xmm0): 入口値は比べない (wasm は 0 と記録する)
    sigs = {'function_40c660': cases.machine_sig(0x40c660, IR_SIG)}
    n = trace(entry('40c660', 1, ['0'], ['3ff8000000000000']))
    assert compare.cmp_trace(n, trace(entry('40c660', 1, ['0'])), CTX, sigs) is None

    # 機械語入口型でない関数 (IR の i128 を含む) は従来どおり比べる
    sigs = {'function_1234': {'ret': 'i64', 'params': ['i64', 'i128'], 'defined': True}}
    r = compare.cmp_trace(trace(entry('1234', 2, ['1', '5'])), trace(entry('1234', 2, ['1', '0'])), CTX, sigs)
    assert r and r['kind'] == 'entry_arg' and r['pos'] == 1, r
    print('PASS test_ld52_machine_sig')


if __name__ == '__main__':
    main()
