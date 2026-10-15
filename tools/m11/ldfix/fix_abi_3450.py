#!/usr/bin/env python3
"""fix_abi_3450.py — #3450 (CI-163): function_41c8c0 (WideCharToMultiByte の薄いラッパ) を 4 引数から 8 引数にし、
呼出元 4 箇所の引数を接続する。引数の並びは機械語の呼出規約どおり (rcx・rdx・r8・r9・5〜8 番目)。

  - 定義: %arg1..%arg4 = rcx・rdx・r8・r9、%arg5..%arg8 = 5〜8 番目 (旧 4 引数は 5〜8 番目だった)。
    WideCharToMultiByte の CodePage・dwFlags・lpWideCharStr・cchWideChar を rcx〜r9 に接続し、
    xor i64 0, 0 の 4 本を除く。
  - 呼出元 (機械語の呼出し直前の rcx〜r9 と照合したもの。照合は verify_abi_3426.check_fixed_machine):
      0x41c2a8 (function_41c260 の 1 site): rcx=CP_UTF8・rdx=0・r8=素通し・r9=素通し・5〜8 番目 = %arg1・%2・0・0
      0x41c352 (function_41c260 の 2 site): rcx=CP_UTF8・rdx=0・r8=素通し・r9=素通し・5〜8 番目 = 0・0・0・0
      0x412ffc (function_412fc0): rdx=0・r8=%arg3 (素通し)・5〜8 番目 = %0・%1・0・0。
        rcx は 5 番目/既定値 (機械語 0x412ff7 mov ecx,eax)、r9 は素通し。どちらも IR (412fc0 の 3 引数) に値が無いため
        0 のまま残す。これは残件 (CI-164 で 412fc0 を 5 引数化して解消する)。
      m11_tr_function_41c8c0: a0..a7 を全て渡す (icall の 8 引数の規約)。

使い方: python3 fix_abi_3450.py IN.ll OUT.ll --pe PE.bin
  機械照合・IR 行の一致のどちらかが外れたら止める (fail-closed)。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import verify_abi_3426 as va  # noqa: E402

REPL = [
    ('define weak i64 @function_41c8c0(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4) local_unnamed_addr {\n',
     'define weak i64 @function_41c8c0(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4, i64 %arg5, i64 %arg6, i64 %arg7, i64 %arg8) local_unnamed_addr {\n',
     1),
    ('  %1 = xor i64 0, 0\n'
     '  %2 = xor i64 0, 0\n'
     '  %3 = xor i64 0, 0\n'
     '  %4 = xor i64 0, 0\n'
     '  %5 = trunc i64 %arg2 to i32\n'
     '  %6 = trunc i64 %4 to i32\n'
     '  %7 = trunc i64 %3 to i32\n'
     '  %8 = inttoptr i64 %2 to ptr\n'
     '  %9 = trunc i64 %1 to i32\n'
     '  %10 = inttoptr i64 %arg1 to ptr\n'
     '  %11 = inttoptr i64 %arg3 to ptr\n'
     '  %12 = inttoptr i64 %arg4 to ptr\n'
     '  %13 = call i32 @WideCharToMultiByte(i32 %6, i32 %7, ptr %8, i32 %9, ptr %10, i32 %5, ptr %11, ptr %12)\n',
     '  %5 = trunc i64 %arg6 to i32\n'
     '  %6 = trunc i64 %arg1 to i32\n'
     '  %7 = trunc i64 %arg2 to i32\n'
     '  %8 = inttoptr i64 %arg3 to ptr\n'
     '  %9 = trunc i64 %arg4 to i32\n'
     '  %10 = inttoptr i64 %arg5 to ptr\n'
     '  %11 = inttoptr i64 %arg7 to ptr\n'
     '  %12 = inttoptr i64 %arg8 to ptr\n'
     '  %13 = call i32 @WideCharToMultiByte(i32 %6, i32 %7, ptr %8, i32 %9, ptr %10, i32 %5, ptr %11, ptr %12)\n',
     1),
    ('  %2 = call i64 @function_41c8c0(i64 %0, i64 %1, i64 0, i64 0)\n',
     '  %2 = call i64 @function_41c8c0(i64 0, i64 0, i64 %arg3, i64 0, i64 %0, i64 %1, i64 0, i64 0)\n',
     1),
    ('  %3 = call i64 @function_41c8c0(i64 %arg1, i64 %2, i64 0, i64 0)\n',
     '  %3 = call i64 @function_41c8c0(i64 65001, i64 0, i64 %arg3, i64 %arg4, i64 %arg1, i64 %2, i64 0, i64 0)\n',
     1),
    ('  %34 = call i64 @function_41c8c0(i64 0, i64 0, i64 0, i64 0)\n',
     '  %34 = call i64 @function_41c8c0(i64 65001, i64 0, i64 %arg3, i64 %arg4, i64 0, i64 0, i64 0, i64 0)\n',
     1),
    ('  %r = call i64 @function_41c8c0(i64 %a0, i64 %a1, i64 %a2, i64 %a3)\n',
     '  %r = call i64 @function_41c8c0(i64 %a0, i64 %a1, i64 %a2, i64 %a3, i64 %a4, i64 %a5, i64 %a6, i64 %a7)\n',
     1),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    m = Machine(a.pe)
    n = va.check_fixed_machine(m)
    print('[fix_abi_3450] 機械照合 OK: %d 項目 (呼出し直前の rcx〜r9 と 0x41c8c0 の素通し)' % n)
    src = open(a.src, errors='replace').read()
    for old, new, cnt in REPL:
        got = src.count(old)
        assert got == cnt, '[fix_abi_3450] 行が %d 件 (想定 %d): %r' % (got, cnt, old[:80])
        src = src.replace(old, new)
    va.check_fixed_ir(src)
    with open(a.dst, 'w') as f:
        f.write(src)
    print('[fix_abi_3450] 修復 OK: 41c8c0 を 8 引数化・呼出元 4 site を接続 (%s)' % a.dst)


if __name__ == '__main__':
    main()
