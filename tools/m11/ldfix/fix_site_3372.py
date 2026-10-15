#!/usr/bin/env python3
"""fix_site_3372.py — #3372 (CI-151): REPORT_2555 §2 の誤り箇所のうち、単純な 1 段 deref 脱落を site 単位で直す。

対象 (機械語 PE .text の VA で指定。各 SITE の EXPECT で機械照合する):
  - function_44f040 (表 #5): 引数 arg1 (rcx) の `*arg1` を 3 箇所で使うのに、IR は arg1 をそのまま使う or 別値を渡す。
      (a) nil 判定と dword[*arg1-4] (長さ): ldfix.py (F1 系) の出力では既に `%ldfxu14` (= load [arg1]) で直っている。
          base IR (ldfix 前) では直っていないので、base 形のときだけ 1 段読みに直す。
      (b) 0x44f095 の 44aeb0 の第 1 引数 `*arg1` (IR は zext dword[arg2-4] を渡す)。
      (c) 0x44f0f6 の 44ec40 の第 3 引数 r8 = `*arg1` (IR は zext dword[arg2-4] を渡す)。44aeb0 が *arg1 を書換えうるので、
          (c) は 44aeb0 の後で改めて読む (`%a1e`)。
  - function_47cf10 (表 #14): 第 1 引数 rcx = `*arg1 + rbx*8`、第 2 引数 rdx = `*arg1 + rbx*8 + 8` だが、IR は arg1 を
      アドレスとして使い (`%20 = %.pre6 + %arg1`)、第 2 引数は `%21 + %20` で rbx*8 を二重に計上している。
      機械語は `mov rcx,[rsp+0x40]; mov rcx,[rcx]` で *arg1 を読む ([rsp+0x40] は 0x47cf1c で rcx=arg1 を 1 回書くだけ)。
      修復: *arg1 を 1 回読み (`%a1f`)、%20 と %22 を `%a1f` 基底に直す。
  - function_6074b0 (表 #15): 機械語は `mov rcx,[rax]` (rax=[rsp+0x40]=arg1) で *arg1 を 4256c0 に渡すが、IR は arg1 を渡す。
      `%a1g` で 1 段読みに直す (1 行の置換)。

機械照合: 各 SITE の EXPECT (VA・mnemonic・operand) を capstone の出力と完全一致で照合し、一致しなければ止める (fail-closed)。
IR 側は、書き換え前の行が関数本体に 1 件ずつ在るときだけ書き換える。二重適用は行が無くなるので止まる。

使い方: python3 fix_site_3372.py IN.ll OUT.ll --pe PE.bin [--negctl {none,double,mach,ir}]
  --negctl はネガティブコントロール用 (double: 二重適用 / mach: 機械照合の改変 / ir: IR base 形の改変)。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ldmach import Machine  # noqa: E402

# (a) base 形 (ldfix 前) の行と 1 段読みへの置換
A_BASE = [
    ('  %6 = icmp eq i64 %arg1, 0\n',
     '  %a1d_p = inttoptr i64 %arg1 to ptr\n'
     '  %a1d = load i64, ptr %a1d_p, align 8\n'
     '  %6 = icmp eq i64 %a1d, 0\n'),
    ('  %7 = add i64 %arg1, -4\n',
     '  %7 = add i64 %a1d, -4\n'),
]
A_LDFIX_ROWS = [
    '  %6 = icmp eq i64 %ldfxu14, 0\n',
    '  %7 = add i64 %ldfxu14, -4\n',
]


def pick_a1(body):
    """(a) の形を判定し、*arg1 の値名と、必要な (a) の置換を返す。"""
    if all(body.count(r[0]) == 1 for r in A_BASE):
        return '%a1d', A_BASE
    if all(body.count(r) == 1 for r in A_LDFIX_ROWS):
        return '%ldfxu14', []
    raise AssertionError('nil/len rows: neither base form nor ldfix form (1 each)')


def edits_44f040(body):
    a1, a_edits = pick_a1(body)
    return a_edits + [
        ('  %19 = call i64 @function_44aeb0(i64 %14, i64 %18)\n',
         '  %19 = call i64 @function_44aeb0(i64 ' + a1 + ', i64 %18)\n'),
        ('  %30 = call i64 @function_44ec40(i64 %arg2, i64 0, i64 %25, ',
         '  %a1e_p = inttoptr i64 %arg1 to ptr\n'
         '  %a1e = load i64, ptr %a1e_p, align 8\n'
         '  %30 = call i64 @function_44ec40(i64 %arg2, i64 0, i64 %a1e, '),
    ]


def edits_47cf10(body):
    return [
        ('  %20 = add i64 %.pre6, %arg1\n',
         '  %a1f_p = inttoptr i64 %arg1 to ptr\n'
         '  %a1f = load i64, ptr %a1f_p, align 8\n'
         '  %20 = add i64 %.pre6, %a1f\n'),
        ('  %22 = add i64 %21, %20\n',
         '  %22 = add i64 %21, %a1f\n'),
    ]


def edits_6074b0(body):
    base = '  %0 = call i64 @function_4256c0(i64 %arg1)\n'
    if body.count(base) == 1:
        return [(base,
                 '  %a1g_p = inttoptr i64 %arg1 to ptr\n'
                 '  %a1g = load i64, ptr %a1g_p, align 8\n'
                 '  %0 = call i64 @function_4256c0(i64 %a1g)\n')]
    if body.count('  %0 = call i64 @function_4256c0(i64 %ldfxu24)\n') == 1:
        return []
    raise AssertionError('call 4256c0 row: neither base form nor ldfix form')


SITES = [
    {
        'fn': 0x44f040,
        'expect': [
            (0x44f064, 'mov', 'rcx, qword ptr [rsp + 0x60]'),
            (0x44f069, 'mov', 'rcx, qword ptr [rcx]'),
            (0x44f071, 'mov', 'eax, dword ptr [rcx - 4]'),
            (0x44f090, 'mov', 'rcx, qword ptr [rax]'),
            (0x44f095, 'call', '0x44aeb0'),
            (0x44f0cb, 'mov', 'r9, qword ptr [rsp + 0x60]'),
            (0x44f0d0, 'mov', 'r9, qword ptr [r9]'),
            (0x44f0f6, 'call', '0x44ec40'),
        ],
        'edits': edits_44f040,
    },
    {
        'fn': 0x47cf10,
        'expect': [
            (0x47cf1c, 'mov', 'qword ptr [rsp + 0x40], rcx'),
            (0x47cf81, 'mov', 'rcx, qword ptr [rsp + 0x40]'),
            (0x47cf86, 'mov', 'rcx, qword ptr [rcx]'),
            (0x47cf89, 'lea', 'rcx, [rcx + rbx*8]'),
            (0x47cf8d, 'mov', 'rdx, qword ptr [rsp + 0x40]'),
            (0x47cf92, 'mov', 'rdx, qword ptr [rdx]'),
            (0x47cf95, 'lea', 'rdx, [rdx + rbx*8 + 8]'),
            (0x47cfa4, 'call', '0x409c80'),
        ],
        'edits': edits_47cf10,
    },
    {
        'fn': 0x6074b0,
        'expect': [
            (0x6074b6, 'mov', 'qword ptr [rsp + 0x40], rcx'),
            (0x6074bb, 'mov', 'rax, qword ptr [rsp + 0x40]'),
            (0x6074c0, 'mov', 'rcx, qword ptr [rax]'),
            (0x6074c3, 'call', '0x4256c0'),
        ],
        'edits': edits_6074b0,
    },
]


def check_machine(pe, site, expect):
    ins = {x.address: x for x in Machine(pe).disasm_fn(site['fn'])}
    for va, mnem, op in expect:
        x = ins.get(va)
        got = None if x is None else (x.mnemonic, x.op_str)
        assert got == (mnem, op), 'machine mismatch at 0x%x: want %r got %r' % (va, (mnem, op), got)
    return len(expect)


def rewrite_site(ir_text, site):
    fn = site['fn']
    m = re.search(r'^define [^\n]*@function_%x\(.*?\n}\n' % fn, ir_text, re.M | re.S)
    assert m, 'function_%x not found in IR' % fn
    body = m.group(0)
    edits = site['edits'](body)
    for old, new in edits:
        n = body.count(old)
        assert n == 1, 'function_%x base row count %d (want 1): %r' % (fn, n, old.strip())
        body = body.replace(old, new)
    return ir_text[:m.start()] + body + ir_text[m.end():], len(edits)


def rewrite_all(ir_text):
    total = 0
    for site in SITES:
        ir_text, n = rewrite_site(ir_text, site)
        total += n
    return ir_text, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir_in')
    ap.add_argument('ir_out')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--negctl', choices=['none', 'double', 'mach', 'ir'], default='none')
    a = ap.parse_args()
    ir = open(a.ir_in, errors='replace').read()
    checks = []
    for site in SITES:
        expect = site['expect']
        if a.negctl == 'mach' and site['fn'] == 0x44f040:
            expect = [(va, mnem, op.replace('[rax]', '[rbx]')) if va == 0x44f090 else (va, mnem, op)
                      for va, mnem, op in expect]
        checks.append((site, expect))
    if a.negctl == 'ir':
        ir = ir.replace('  %19 = call i64 @function_44aeb0(i64 %14, i64 %18)\n',
                        '  %19 = call i64 @function_44aeb0(i64 %13, i64 %18)\n', 1)
    if a.negctl == 'double':
        ir, _ = rewrite_all(ir)
    n_m = sum(check_machine(a.pe, s, e) for s, e in checks)
    out, n_e = rewrite_all(ir)
    open(a.ir_out, 'w').write(out)
    print('fix_site_3372: machine checks %d ok (%d sites), IR edits %d applied -> %s'
          % (n_m, len(SITES), n_e, a.ir_out))


if __name__ == '__main__':
    main()
