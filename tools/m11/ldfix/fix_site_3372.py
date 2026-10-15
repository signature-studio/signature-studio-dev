#!/usr/bin/env python3
"""fix_site_3372.py — #3372 (CI-151): REPORT_2555 §2 の誤り箇所のうち function_44f040 (表 #5) の 1 段 deref 脱落を直す。

機械語 (PE VA 0x44f040・.text) は引数 arg1 (rcx) を `mov rcx,[rsp+0x60]; mov rcx,[rcx]` で 1 段読んで `*arg1` を得る。
それを次の 3 箇所で使う (いずれも機械語で確認済み。EXPECT 参照):
  (a) 0x44f069・0x44f071: `*arg1` の nil 判定と dword[*arg1-4] (長さ)。
      ldfix.py (F1 系) の出力では既に `%ldfxu14` (= load [arg1]) で直っている。base IR (ldfix 前) では直っていない。
  (b) 0x44f090・0x44f095: 44aeb0 の第 1 引数 `*arg1`。base IR と ldfix 出力のどちらも zext dword[arg2-4] を渡している。
  (c) 0x44f0cb〜0x44f0f6: 44ec40 の第 3 引数 r8 = `*arg1`。同じく base と ldfix 出力のどちらも zext dword[arg2-4]。
      44aeb0 が *arg1 を書き換えうるため、(c) は 44aeb0 の後で改めて読む (`%a1e`)。

修復は (a) を base 形のときだけ 1 段読みに直し、(b)(c) を直す。(a) が ldfix 済みの形なら、その値名を使う。
機械照合: 上の命令 (VA・mnemonic・operand) を capstone の出力と完全一致で照合し、一致しなければ止める (fail-closed)。
IR 側は、書き換える行が関数本体に 1 件ずつ在るときだけ書き換える。二重適用は行が無くなるので止まる。

使い方: python3 fix_site_3372.py IN.ll OUT.ll --pe PE.bin [--negctl {none,double,mach,ir}]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ldmach import Machine  # noqa: E402

FN_VA = 0x44f040
FN = re.compile(r'^define [^\n]*@function_44f040\(.*?\n}\n', re.M | re.S)

# 機械語で照合する命令 (VA, mnemonic, op_str)。capstone の出力文字列と完全一致させる
EXPECT = [
    (0x44f064, 'mov', 'rcx, qword ptr [rsp + 0x60]'),
    (0x44f069, 'mov', 'rcx, qword ptr [rcx]'),
    (0x44f071, 'mov', 'eax, dword ptr [rcx - 4]'),
    (0x44f090, 'mov', 'rcx, qword ptr [rax]'),
    (0x44f095, 'call', '0x44aeb0'),
    (0x44f0cb, 'mov', 'r9, qword ptr [rsp + 0x60]'),
    (0x44f0d0, 'mov', 'r9, qword ptr [r9]'),
    (0x44f0f6, 'call', '0x44ec40'),
]

# (a) base 形 (ldfix 前) の行と 1 段読みへの置換
A_BASE = [
    ('  %6 = icmp eq i64 %arg1, 0\n',
     '  %a1d_p = inttoptr i64 %arg1 to ptr\n'
     '  %a1d = load i64, ptr %a1d_p, align 8\n'
     '  %6 = icmp eq i64 %a1d, 0\n'),
    ('  %7 = add i64 %arg1, -4\n',
     '  %7 = add i64 %a1d, -4\n'),
]
A_BASE_ROWS = [r[0] for r in A_BASE]
A_LDFIX_ROWS = [
    '  %6 = icmp eq i64 %ldfxu14, 0\n',
    '  %7 = add i64 %ldfxu14, -4\n',
]


def pick_a1(body):
    """(a) の形を判定し、*arg1 の値名と、必要な (a) の置換を返す。"""
    if all(body.count(r) == 1 for r in A_BASE_ROWS):
        return '%a1d', A_BASE
    if all(body.count(r) == 1 for r in A_LDFIX_ROWS):
        return '%ldfxu14', []
    raise AssertionError('nil/len rows: neither base form nor ldfix form (1 each)')


def bc_edits(a1):
    return [
        ('  %19 = call i64 @function_44aeb0(i64 %14, i64 %18)\n',
         '  %19 = call i64 @function_44aeb0(i64 ' + a1 + ', i64 %18)\n'),
        ('  %30 = call i64 @function_44ec40(i64 %arg2, i64 0, i64 %25, ',
         '  %a1e_p = inttoptr i64 %arg1 to ptr\n'
         '  %a1e = load i64, ptr %a1e_p, align 8\n'
         '  %30 = call i64 @function_44ec40(i64 %arg2, i64 0, i64 %a1e, '),
    ]


def check_machine(pe, expect):
    ins = {x.address: x for x in Machine(pe).disasm_fn(FN_VA)}
    for va, mnem, op in expect:
        x = ins.get(va)
        got = None if x is None else (x.mnemonic, x.op_str)
        assert got == (mnem, op), 'machine mismatch at 0x%x: want %r got %r' % (va, (mnem, op), got)
    return len(expect)


def rewrite(ir_text):
    m = FN.search(ir_text)
    assert m, 'function_44f040 not found in IR'
    body = m.group(0)
    a1, a_edits = pick_a1(body)
    edits = a_edits + bc_edits(a1)
    for old, new in edits:
        n = body.count(old)
        assert n == 1, 'base row count %d (want 1): %r' % (n, old.strip())
        body = body.replace(old, new)
    return ir_text[:m.start()] + body + ir_text[m.end():], len(edits), a1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir_in')
    ap.add_argument('ir_out')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--negctl', choices=['none', 'double', 'mach', 'ir'], default='none')
    a = ap.parse_args()
    ir = open(a.ir_in, errors='replace').read()
    expect = EXPECT
    if a.negctl == 'mach':
        expect = [(va, mnem, op.replace('[rax]', '[rbx]')) if va == 0x44f090 else (va, mnem, op)
                  for va, mnem, op in EXPECT]
    if a.negctl == 'ir':
        ir = ir.replace('  %19 = call i64 @function_44aeb0(i64 %14, i64 %18)\n',
                        '  %19 = call i64 @function_44aeb0(i64 %13, i64 %18)\n', 1)
    if a.negctl == 'double':
        ir, _, _ = rewrite(ir)
    n_m = check_machine(a.pe, expect)
    out, n_e, a1 = rewrite(ir)
    open(a.ir_out, 'w').write(out)
    print('fix_site_3372: machine checks %d ok, IR edits %d applied (*arg1 = %s) -> %s'
          % (n_m, n_e, a1, a.ir_out))


if __name__ == '__main__':
    main()
