#!/usr/bin/env python3
"""thunk_FUN_ 写像の正例・負例 (合成入力)。ghidra_to_c.py の thunk_targets / rewrite_thunks を直接検証する。

  python3 tools/targets/kilohearts/ghidra_route/thunk_map_check.py

正例: 定義ヘッダの thunk_FUN_<X> は自分の FUN_<T> になり、本体の呼出 thunk_FUN_<X> は thunk の FUN_<T> へ写る (自己再帰にならない)。
負例: 写し先が無い / 一意でない呼出は SystemExit で停止する (fail-closed)。
対照: 旧実装 (`thunk_FUN_[0-9a-f]+` を全置換して呼出元の VA にする) は正例2 で失敗する (本テストが旧バグを検出する)。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghidra_to_c as g

CALLER = 0x1802ed3b0   # 呼出元 (本体に thunk_FUN_1802ed7f0 を 2 件持つ)
PROC = 0x1802ed7f0     # 飛び先 X
T1 = 0x180f8791c       # X へ jmp する thunk
T2 = 0x180f87cac       # 同じ X へ jmp する 2 本目の thunk (負例用)

CALLER_C = """void FUN_1802ed3b0(longlong param_1,int param_2)

{
  thunk_FUN_1802ed7f0(param_1,0);
  thunk_FUN_1802ed7f0(param_1,param_2);
  return;
}
"""
THUNK_C = """void thunk_FUN_1802ed7f0(longlong param_1,int param_2)

{
  FUN_1802ed7f0(param_1,param_2);
  return;
}
"""
PROC_C = """void FUN_1802ed7f0(longlong param_1,int param_2)

{
  return;
}
"""


def expect_stop(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


def main():
    results = []

    def check(name, cond):
        results.append(bool(cond))
        print('%s %s' % ('PASS' if cond else 'FAIL', name))

    thunk_of = g.thunk_targets({CALLER: CALLER_C, T1: THUNK_C, PROC: PROC_C})
    check('thunk_targets: 定義ヘッダだけを見る (呼出は数えない)', thunk_of == {T1: PROC})

    out = g.rewrite_thunks(CALLER_C, CALLER, thunk_of)
    check('正例1: 呼出 thunk_FUN_1802ed7f0 が thunk の FUN_180f8791c に 2 件写る', out.count('FUN_%x(' % T1) == 2 and 'thunk_FUN_' not in out)
    check('正例2: 呼出元の自己再帰を作らない (本体に FUN_1802ed3b0 への写像 0 件)', 'FUN_%x(' % CALLER not in out.split('{', 1)[1])
    check('正例3: 呼出元の定義ヘッダは書き換えない', out.startswith('void FUN_%x(' % CALLER))

    out_t = g.rewrite_thunks(THUNK_C, T1, thunk_of)
    check('正例4: thunk 自身の定義ヘッダ thunk_FUN_1802ed7f0 は FUN_180f8791c になる', out_t.startswith('void FUN_%x(' % T1) and 'thunk_FUN_' not in out_t)

    check('負例1: 写し先の thunk が無い呼出は停止', expect_stop(lambda: g.rewrite_thunks(CALLER_C, CALLER, {})))
    check('負例2: 写し先の thunk が 2 本ある呼出は停止', expect_stop(lambda: g.rewrite_thunks(CALLER_C, CALLER, {T1: PROC, T2: PROC})))
    check('負例3: 別の X (1802ed7f8) の呼出は、X に対応する thunk が無いので停止', expect_stop(lambda: g.rewrite_thunks(
        CALLER_C.replace('thunk_FUN_1802ed7f0(param_1,param_2)', 'thunk_FUN_1802ed7f8(param_1,param_2)'), CALLER, thunk_of)))

    old = re.sub(r'\bthunk_FUN_[0-9a-f]+\b', 'FUN_%x' % CALLER, CALLER_C)
    check('対照: 旧実装 (全置換) は正例2 で自己再帰を作る (本テストで検出できる)', 'FUN_%x(' % CALLER in old.split('{', 1)[1])

    n_ok = sum(results)
    print('RESULT %d/%d' % (n_ok, len(results)))
    return 0 if n_ok == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
