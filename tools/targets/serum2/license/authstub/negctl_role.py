#!/usr/bin/env python3
"""役割導出 (derive_role) のネガティブコントロール (#1208)。

合成 IR 1 関数に対して、役割導出が
  正例 (icmp eq の比較値)            → tag_len
  正例 (key 検索 call の第 1 引数)    → dom
  正例 (ucomisd の被演算子)           → dbl
  負例 (役割が 2 種混在)              → SystemExit (roles disagree)
  負例 (未分類の使用が 1 件あり)       → SystemExit (undecided)
  負例 (使用 0 件)                   → SystemExit (undecided: roles=[])
となることを確認する。全て満たせば exit 0。

usage: python3 negctl_role.py
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'liftlib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authstub_irpass import derive_role

FN = 0x1800c2c00
NAME = '%70'


def fn(body):
    return [f'define void @function_{FN:x}() {{', '  %1 = alloca i64'] + body + ['  ret void', '}']


CASES = {
    'tag_len': fn([f'  %70 = load i64, ptr %stack_var_-72',
                   '  %71 = icmp eq i64 %70, 10']),
    'dom': fn([f'  %70 = load i64, ptr %stack_var_-72',
               '  %71 = call i64 @function_180023360(i64 %70, ptr getelementptr inbounds ([12 x i8], ptr @global_var_180fc8ff8, i64 0, i64 0))']),
    'dbl': fn([f'  %70 = load i64, ptr %stack_var_-72',
               '  call void @__asm_ucomisd(i128 %70, i128 %3)']),
}
MIXED = fn([f'  %70 = load i64, ptr %stack_var_-72',
            '  %71 = icmp eq i64 %70, 10',
            '  call void @__asm_ucomisd(i128 %70, i128 %3)'])
UNKNOWN = fn([f'  %70 = load i64, ptr %stack_var_-72',
              '  %71 = icmp eq i64 %70, 10',
              '  %72 = add i64 %70, 1'])
NONE = fn([f'  %70 = load i64, ptr %stack_var_-72'])


def run(lines):
    try:
        return True, derive_role(lines, FN, NAME, 'T')
    except SystemExit as e:
        return False, str(e)


for role, lines in CASES.items():
    ok, got = run(lines)
    if not ok or got != role:
        raise SystemExit(f'positive control ({role}) failed: {got}')
    print(f'PASS  正例 {role}: derive_role = {got}')

for label, lines in (('混在', MIXED), ('未分類', UNKNOWN), ('使用 0 件', NONE)):
    ok, msg = run(lines)
    if ok:
        raise SystemExit(f'negative control ({label}) did not fail')
    print(f'FAIL  負例 {label}: {msg[:120]}')
print('negctl_role OK')
