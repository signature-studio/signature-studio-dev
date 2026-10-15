#!/usr/bin/env python3
"""fix_site_3418.py — #3418 (CI-156): REPORT_2555 表 #13 (0x47b4a0) と #16 (0xc40770) の複雑型の誤りを site 単位で直す。

対象 (機械語 PE .text の VA で指定。各 SITE の EXPECT で機械照合する):
  - function_47b4a0 (表 #13): call 0x409c80 の第 2 引数は `*arg1 + rsi*r8` (機械語 0x47b4f0〜0x47b503)。
      IR の `%24 = %23 + %arg2` は基底が arg2 で、`*arg1` の読出しが無い。`*arg1` を 1 回読んで基底にする (`%a1h`)。
  - function_c40770 (表 #16): call 0x409c80 の第 2 引数は `*arg4 + 52*count - 24` (機械語 0xc409bb〜0xc409d6)。
      count は `[*arg4 - 8]`。IR は基底に `%173` (0x4776e0 の戻り値) を使っていて、機械語の `*arg4` と一致しない。
      null 判定 (`je 0xc409b7`: `[*arg4] == 0` で `rax=0` のまま) も `*arg4` の値で分岐するので、`%183`・`%184`・`%189` を
      `*arg4` の読出し (`%a4v`) に直す。格納先 (0xc409f1) は call の後で `*arg4` を読み直すので、`%199` の直前で再読出し (`%a4w`) する。
      null 経路の 2 つ目の call (-24) は `*arg4 == 0` の分岐の下にあり、IR の定数のままで正しい。

機械照合: 各 SITE の EXPECT (VA・mnemonic・operand) を capstone の出力と完全一致で照合し、一致しなければ止める (fail-closed)。
IR 側は、書き換え前の行が関数本体に 1 件ずつ在るときだけ書き換える。二重適用は行が無くなるので止まる。

使い方: python3 fix_site_3418.py IN.ll OUT.ll --pe PE.bin [--negctl {none,double,mach,ir}]
  --negctl はネガティブコントロール用 (double: 二重適用 / mach: 機械照合の改変 / ir: IR base 形の改変)。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_site_3372 import check_machine, rewrite_site  # noqa: E402


def edits_47b4a0(body):
    return [
        ('  %24 = add i64 %23, %arg2\n',
         '  %a1h_p = inttoptr i64 %arg1 to ptr\n'
         '  %a1h = load i64, ptr %a1h_p, align 8\n'
         '  %24 = add i64 %23, %a1h\n'),
    ]


def edits_c40770(body):
    return [
        ('  %183 = icmp eq i64 %173, 0\n',
         '  %a4v_p = inttoptr i64 %arg4 to ptr\n'
         '  %a4v = load i64, ptr %a4v_p, align 8\n'
         '  %183 = icmp eq i64 %a4v, 0\n'),
        ('  %184 = add nsw i64 %173, -8\n',
         '  %184 = add nsw i64 %a4v, -8\n'),
        ('  %189 = add nsw i64 %173, -24\n',
         '  %189 = add nsw i64 %a4v, -24\n'),
        ('  %199 = add nsw i64 %173, -4\n',
         '  %a4w_p = inttoptr i64 %arg4 to ptr\n'
         '  %a4w = load i64, ptr %a4w_p, align 8\n'
         '  %199 = add nsw i64 %a4w, -4\n'),
    ]


SITES = [
    {
        'fn': 0x47b4a0,
        'expect': [
            (0x47b4f0, 'mov', 'rdx, qword ptr [rsp + 0x40]'),
            (0x47b4f5, 'mov', 'rdx, qword ptr [rdx]'),
            (0x47b503, 'lea', 'rdx, [rdx + r9]'),
            (0x47b50b, 'call', '0x409c80'),
        ],
        'edits': edits_47b4a0,
    },
    {
        'fn': 0xc40770,
        'expect': [
            (0xc409a6, 'mov', 'rax, qword ptr [rsp + 0x30]'),
            (0xc409ab, 'mov', 'rax, qword ptr [rax]'),
            (0xc409b3, 'mov', 'rax, qword ptr [rax - 8]'),
            (0xc409bb, 'mov', 'rdx, qword ptr [rsp + 0x30]'),
            (0xc409c0, 'mov', 'rdx, qword ptr [rdx]'),
            (0xc409cb, 'lea', 'rdx, [rdx + rax*4 + 0x1c]'),
            (0xc409d6, 'call', '0x409c80'),
            (0xc409ec, 'mov', 'rcx, qword ptr [rsp + 0x30]'),
            (0xc409f1, 'mov', 'rcx, qword ptr [rcx]'),
        ],
        'edits': edits_c40770,
    },
]


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
    for i, site in enumerate(SITES):
        expect = site['expect']
        if a.negctl == 'mach' and i == 0:
            expect = [(va, mnem, op.replace('[rdx]', '[rcx]')) if va == 0x47b4f5 else (va, mnem, op)
                      for va, mnem, op in expect]
        checks.append((site, expect))
    if a.negctl == 'ir':
        ir = ir.replace('  %24 = add i64 %23, %arg2\n', '  %24 = add i64 %23, %arg1\n', 1)
    if a.negctl == 'double':
        ir, _ = rewrite_all(ir)
    n_m = sum(check_machine(a.pe, s, e) for s, e in checks)
    out, n_e = rewrite_all(ir)
    open(a.ir_out, 'w').write(out)
    print('fix_site_3418: machine checks %d ok (%d sites), IR edits %d applied -> %s'
          % (n_m, len(SITES), n_e, a.ir_out))


if __name__ == '__main__':
    main()
