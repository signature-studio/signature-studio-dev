#!/usr/bin/env python3
"""fix_abi_4522.py — #4522 (CI-192): 呼出元 0x413340 の 2 site の r8・r9 を機械語の値へ接続する。

#4521 (CI-191) の後の残件。412fc0 は rcx・rdx・r8・r9・5 番目の 5 引数になったが、0x413340 の 2 site は
r8・r9 を 0 のまま渡していた。機械語の値へ置き換える。

  - site 1 (0x41338b): r8 = [rsp+0x38] = 0x413340 の arg2 (0x41334e で保存)
                       r9 = ebx = zext(arg3 の下位 32 bit) (0x413353 で保存、0x41338b まで ebx は不変)
  - site 2 (0x4133bc): r8 = [rsp+0x38] = arg2、r9 = ebx (0x4133b4 の mov r9d,ebx)
  - rcx は site 1 が 0、site 2 が *(arg1) (fix_site_3326.py が接続済み)。rdx・5 番目は触らない。

照合 (fail-closed): 機械語 (capstone) の呼出し直前の区間を全命令で完全一致させてから IR を書き換える。
IR は該当行が 1 件だけ一致するときだけ書き換え、適用済みの IR は拒否する。

使い方: python3 fix_abi_4522.py IN.ll OUT.ll --pe PE.bin
  4521 の修復 (fix_abi_4521.py) の後に通すこと。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import verify_abi_3426 as va  # noqa: E402

# 機械語: 呼出し直前の区間 (VA・mnemonic・operand の完全一致)。最後の call は 0x412fc0。
SITES = [
    dict(name='site1 (0x41338b)', start=0x41337a, call=0x41338b, machine=[
        (0x41337a, 'xor', 'ecx, ecx'),
        (0x41337c, 'xor', 'edx, edx'),
        (0x41337e, 'mov', 'r8, qword ptr [rsp + 0x38]'),
        (0x413383, 'mov', 'r9d, ebx'),
        (0x413386, 'mov', 'dword ptr [rsp + 0x20], r13d'),
    ]),
    dict(name='site2 (0x4133bc)', start=0x4133a5, call=0x4133bc, machine=[
        (0x4133a5, 'mov', 'rax, qword ptr [rsp + 0x30]'),
        (0x4133aa, 'mov', 'rcx, qword ptr [rax]'),
        (0x4133ad, 'mov', 'edx, edi'),
        (0x4133af, 'mov', 'r8, qword ptr [rsp + 0x38]'),
        (0x4133b4, 'mov', 'r9d, ebx'),
        (0x4133b7, 'mov', 'dword ptr [rsp + 0x20], r13d'),
    ]),
]

# IR (4521 修復後の行。どちらも 1 件だけ一致)。r9 = zext(%0)、%0 = trunc arg3 (0x413340 の入口)。
REPL = [
    ('  %15 = call i64 @function_412fc0(i32 0, i32 0, i64 0, i64 0, i64 %14)\n',
     '  %ldfx4522_r9a = zext i32 %0 to i64\n'
     '  %15 = call i64 @function_412fc0(i32 0, i32 0, i64 %arg2, i64 %ldfx4522_r9a, i64 %14)\n',
     1),
    ('  %21 = call i64 @function_412fc0(i32 %20, i32 %18, i64 0, i64 0, i64 %14)\n',
     '  %ldfx4522_r9b = zext i32 %0 to i64\n'
     '  %21 = call i64 @function_412fc0(i32 %20, i32 %18, i64 %arg2, i64 %ldfx4522_r9b, i64 %14)\n',
     1),
]


def check_machine(m):
    """機械語: 2 site の呼出し直前の区間 (rcx・rdx・r8・r9・5 番目) を全命令で照合する。"""
    n = 0
    for s in SITES:
        seq = [(i.address, i.mnemonic, i.op_str) for i in va.insns(m, s['start'], s['call'] + 1)]
        want = s['machine'] + [(s['call'], 'call', '0x412fc0')]
        assert seq == want, '%s: 呼出し直前の区間が想定と違う: %r != %r' % (s['name'], seq, want)
        n += len(want)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    m = Machine(a.pe)
    n = check_machine(m)
    print('[fix_abi_4522] 機械照合 OK: %d 項目 (0x413340 の 2 site の rcx〜r9・5 番目)' % n)
    src = open(a.src, errors='replace').read()
    for old, new, cnt in REPL:
        got = src.count(old)
        assert got == cnt, '[fix_abi_4522] 行が %d 件 (想定 %d): %r' % (got, cnt, old[:80])
        src = src.replace(old, new)
    with open(a.dst, 'w') as f:
        f.write(src)
    print('[fix_abi_4522] 修復 OK: 0x413340 の 2 site の r8・r9 を接続 (%s)' % a.dst)


if __name__ == '__main__':
    main()
