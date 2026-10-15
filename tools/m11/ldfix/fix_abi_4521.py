#!/usr/bin/env python3
"""fix_abi_4521.py — #4521 (CI-191): function_412fc0 を 3 引数から 5 引数 (rcx・rdx・r8・r9・5 番目) にし、
5 番目が 0 のとき 0x15e6a28 の既定値を使う分岐を入れる。呼出元 3 箇所を新しい引数列に合わせる。

  - 定義: %arg1 = rcx, %arg2 = rdx, %arg3 = r8, %arg4 = r9, %arg5 = 5 番目 (入口 [rsp+0x28])。
    機械語 0x412fc4〜0x412fd5: cmp dword [rsp+0x70],0 → 0 なら mov eax,[0x15e6a28]; mov [rsp+0x70],eax。
    0x41c8c0 へは rcx = zext(5 番目または既定値)・rdx = 0・r8 = %arg3・r9 = %arg4 (素通し)、
    スタック 5〜8 番目 = %0・%1・0・0 (機械語 0x412fdc〜0x412fee)。
  - 呼出元: 0x413340 の 2 site は 5 番目 (%14 = movzx si) を 5 番目の位置へ入れ、r8・r9 は 0 のまま
    (機械語の r8・r9 の接続は CI-192 の範囲)。m11_tr_function_412fc0 は a0〜a4 を渡す (rcx〜r9 と 5 番目)。
  - 照合: verify_abi_3426.check_fixed_machine (機械語) と verify_default_global (既定値の参照先) を先に通す (fail-closed)。
    IR は 412fc0 の形と呼出元 3 site の 5 番目を assert する (verify_abi_3426.check_fixed_412)。

使い方: python3 fix_abi_4521.py IN.ll OUT.ll --pe PE.bin
  3450 の修復 (fix_abi_3450.py) の後に通すこと (412fc0 の 41c8c0 呼出し行が 3450 の出力を前提にする)。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import verify_abi_3426 as va  # noqa: E402

REPL = [
    ('define weak i64 @function_412fc0(i32 %arg1, i32 %arg2, i64 %arg3) local_unnamed_addr {\n'
     'dec_label_pc_412fc0:\n'
     '  %0 = sext i32 %arg1 to i64\n'
     '  %1 = sext i32 %arg2 to i64\n'
     '  %2 = call i64 @function_41c8c0(i64 0, i64 0, i64 %arg3, i64 0, i64 %0, i64 %1, i64 0, i64 0)\n'
     '  ret i64 %2\n'
     '}\n',
     'define weak i64 @function_412fc0(i32 %arg1, i32 %arg2, i64 %arg3, i64 %arg4, i64 %arg5) local_unnamed_addr {\n'
     'dec_label_pc_412fc0:\n'
     '  %v5.reg2mem = alloca i32, align 4\n'
     '  %0 = sext i32 %arg1 to i64\n'
     '  %1 = sext i32 %arg2 to i64\n'
     '  %c5 = trunc i64 %arg5 to i32\n'
     '  store i32 %c5, ptr %v5.reg2mem, align 4\n'
     '  %z5 = icmp eq i32 %c5, 0\n'
     '  br i1 %z5, label %dec_label_pc_412fcb, label %dec_label_pc_412fd5\n'
     '\n'
     'dec_label_pc_412fcb:\n'
     '  %d5 = load i32, ptr inttoptr (i64 22964776 to ptr), align 4\n'
     '  store i32 %d5, ptr %v5.reg2mem, align 4\n'
     '  br label %dec_label_pc_412fd5\n'
     '\n'
     'dec_label_pc_412fd5:\n'
     '  %v5 = load i32, ptr %v5.reg2mem, align 4\n'
     '  %r5 = zext i32 %v5 to i64\n'
     '  %2 = call i64 @function_41c8c0(i64 %r5, i64 0, i64 %arg3, i64 %arg4, i64 %0, i64 %1, i64 0, i64 0)\n'
     '  ret i64 %2\n'
     '}\n',
     1),
    ('  %15 = call i64 @function_412fc0(i32 0, i32 0, i64 %14)\n',
     '  %15 = call i64 @function_412fc0(i32 0, i32 0, i64 0, i64 0, i64 %14)\n',
     1),
    ('  %21 = call i64 @function_412fc0(i32 %20, i32 %18, i64 %14)\n',
     '  %21 = call i64 @function_412fc0(i32 %20, i32 %18, i64 0, i64 0, i64 %14)\n',
     1),
    ('  %r = call i64 @function_412fc0(i32 %c0, i32 %c1, i64 %a2)\n',
     '  %r = call i64 @function_412fc0(i32 %c0, i32 %c1, i64 %a2, i64 %a3, i64 %a4)\n',
     1),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    m = Machine(a.pe)
    n = va.check_fixed_machine(m) + va.verify_default_global(m)
    print('[fix_abi_4521] 機械照合 OK: %d 項目 (412fc0 の rcx〜r9・既定値の参照先)' % n)
    src = open(a.src, errors='replace').read()
    for old, new, cnt in REPL:
        got = src.count(old)
        assert got == cnt, '[fix_abi_4521] 行が %d 件 (想定 %d): %r' % (got, cnt, old[:80])
        src = src.replace(old, new)
    va.check_fixed_412(src)
    with open(a.dst, 'w') as f:
        f.write(src)
    print('[fix_abi_4521] 修復 OK: 412fc0 を 5 引数化・既定値分岐・呼出元 3 site (%s)' % a.dst)


if __name__ == '__main__':
    main()
