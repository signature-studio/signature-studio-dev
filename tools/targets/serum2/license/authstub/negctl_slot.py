#!/usr/bin/env python3
"""bind_load_slot_at の照合ネガティブコントロール (SR-11)。

合成 IR 1 関数 (`!insn.addr` 付き) に対して bind_load_slot_at を呼び、
  正例 (VA・期待 slot が一致)   → PASS (行が @glob に置換される)
  誤 slot (期待 slot が不一致)  → SystemExit (slot 照合で FAIL)
  誤 VA (site 0 件)            → SystemExit (candidate = 0)
を確認する。全て満たせば exit 0。

usage: python3 negctl_slot.py
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'liftlib'))
from liftlib.passes.fp_bind import bind_load_slot_at

FN = 0x1800c2c00
VA = 0x1800c2c94
IR = [
    f'define void @function_{FN:x}() {{',
    '  %1 = alloca i64',
    '  %2 = load i64, ptr %stack_var_-72, !insn.addr !10',
    '  ret void',
    '}',
    f'!10 = !{{i64 {VA}}}',
]


def run(va, expect):
    lines = list(IR)
    try:
        bind_load_slot_at(lines, FN, va, expect, '__authstub_doc_root', 'T')
    except SystemExit as e:
        return False, str(e)
    return True, lines[2]


ok, msg = run(VA, '-72')
if not ok or '@__authstub_doc_root' not in msg or 'LIFTFIX T' not in msg:
    raise SystemExit(f'positive control failed: {msg}')
print('PASS  正例:', msg.strip())

ok, msg = run(VA, '-80')
if ok:
    raise SystemExit('negative control (wrong slot) did not fail')
print('FAIL  誤 slot:', msg)

ok, msg = run(VA + 1, '-72')
if ok:
    raise SystemExit('negative control (wrong VA) did not fail')
print('FAIL  誤 VA:', msg)
print('negctl_slot OK')
