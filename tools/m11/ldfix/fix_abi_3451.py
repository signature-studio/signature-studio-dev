#!/usr/bin/env python3
"""fix_abi_3451.py — #3451 (CI-164): function_412fc0 を機械語の引数形 (rcx・rdx・r8・r9・5 番目) の 5 引数にし、
5 番目が 0 のとき既定値 global (VA 0x15e6a28 = IR 上 18770472) を使う分岐を入れる。呼出元 3 site を付け直す。

  - 定義 (0x412fc0): CodePage = zext(5 番目 or 既定値)・dwFlags = 0・lpWideCharStr = r8・cchWideChar = r9・
    lpMultiByteStr = rcx (stack 5)・cbMultiByte = rdx (stack 6)。
  - 呼出元 0x413340 site1 (0x41338b): rcx=0・rdx=0・r8=arg2・r9=zext(arg3)・5 番目=%14 (zext16 si)。
  - 呼出元 0x413340 site2 (0x412fc0 call 0x4133bc): rcx=*(arg1)・rdx=zext(%15)・r8=arg2・r9=zext(arg3)・5 番目=%14。
  - 呼出元 m11_tr_function_412fc0: a0..a4 を渡す (icall の 8 引数の規約)。

機械照合 (check_fixed3_machine) は呼出し直前の値を capstone で確かめる (gate。照合が外れたら止める)。
前段は fix_abi_3450.py (41c8c0 の 8 引数化) を前提とする。

使い方: python3 fix_abi_3451.py IN.ll OUT.ll --pe PE.bin [--negctl]
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import verify_abi_3426 as va  # noqa: E402

DEFAULT_IR = 18770472  # 0x15e6a28 - 0x400000
REL_DEFAULT_VA = 0x15e6a28

SITE1_CALL = 0x41338b
SITE2_CALL = 0x4133bc

REPL = [
    ('define weak i64 @function_412fc0(i32 %arg1, i32 %arg2, i64 %arg3) local_unnamed_addr {\n'
     'dec_label_pc_412fc0:\n'
     '  %0 = sext i32 %arg1 to i64\n'
     '  %1 = sext i32 %arg2 to i64\n'
     '  %2 = call i64 @function_41c8c0(i64 0, i64 0, i64 %arg3, i64 0, i64 %0, i64 %1, i64 0, i64 0)\n'
     '  ret i64 %2\n'
     '}\n',
     'define weak i64 @function_412fc0(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4, i64 %arg5) local_unnamed_addr {\n'
     'dec_label_pc_412fc0:\n'
     '  %p5 = trunc i64 %arg5 to i32\n'
     '  %dflt = load i32, ptr inttoptr (i64 18770472 to ptr), align 4\n'
     '  %p5z = icmp eq i32 %p5, 0\n'
     '  %cp32 = select i1 %p5z, i32 %dflt, i32 %p5\n'
     '  %cp = zext i32 %cp32 to i64\n'
     '  %2 = call i64 @function_41c8c0(i64 %cp, i64 0, i64 %arg3, i64 %arg4, i64 %arg1, i64 %arg2, i64 0, i64 0)\n'
     '  ret i64 %2\n'
     '}\n',
     1),
    ('  %15 = call i64 @function_412fc0(i32 0, i32 0, i64 %14)\n',
     '  %r9a = and i64 %arg3, 4294967295\n'
     '  %15 = call i64 @function_412fc0(i64 0, i64 0, i64 %arg2, i64 %r9a, i64 %14)\n',
     1),
    ('  %20 = trunc i64 %ldfx3326a to i32\n'
     '  %21 = call i64 @function_412fc0(i32 %20, i32 %18, i64 %14)\n',
     '  %r9b = and i64 %arg3, 4294967295\n'
     '  %21 = call i64 @function_412fc0(i64 %ldfx3326a, i64 %16, i64 %arg2, i64 %r9b, i64 %14)\n',
     1),
    ('  %c0 = trunc i64 %a0 to i32\n'
     '  %c1 = trunc i64 %a1 to i32\n'
     '  %r = call i64 @function_412fc0(i32 %c0, i32 %c1, i64 %a2)\n',
     '  %r = call i64 @function_412fc0(i64 %a0, i64 %a1, i64 %a2, i64 %a3, i64 %a4)\n',
     1),
]


def window(m, start, call, expect, target, name):
    """start から call までが expect と一致し、call の対象が target であること (直線区間の完全一致)"""
    seq = []
    for i in va.disasm(m, start, call - start + 16):
        seq.append((i.address, i.mnemonic, i.op_str))
        if i.address == call:
            break
    want = list(expect) + [(call, 'call', target)]
    assert seq == want, '%s: 呼出し直前の区間が想定と違う: %r != %r' % (name, seq, want)
    return len(want)


def check_fixed3_machine(m):
    n = va.verify_machine(m, va.FN_A, va.MACHINE_A, '0x412fc0')
    n += va.verify_default_global(m)
    n += va.check_fixed_machine(m)
    # 0x413340 site1: rcx=0・rdx=0・r8=arg2 (rdx の退避)・r9=zext(ebx)=zext(arg3)・5 番目=r13d (zext si)
    n += window(m, 0x413376, SITE1_CALL, [
        (0x413376, 'movzx', 'r13d, si'), (0x41337a, 'xor', 'ecx, ecx'), (0x41337c, 'xor', 'edx, edx'),
        (0x41337e, 'mov', 'r8, qword ptr [rsp + 0x38]'), (0x413383, 'mov', 'r9d, ebx'),
        (0x413386, 'mov', 'dword ptr [rsp + 0x20], r13d')], '0x412fc0', '0x413340 site1')
    # 0x413340 site2: rcx=*(arg1)・rdx=edi (site1 の結果)・r8=arg2・r9=zext(ebx)・5 番目=r13d
    n += window(m, 0x4133a5, SITE2_CALL, [
        (0x4133a5, 'mov', 'rax, qword ptr [rsp + 0x30]'), (0x4133aa, 'mov', 'rcx, qword ptr [rax]'),
        (0x4133ad, 'mov', 'edx, edi'), (0x4133af, 'mov', 'r8, qword ptr [rsp + 0x38]'),
        (0x4133b4, 'mov', 'r9d, ebx'), (0x4133b7, 'mov', 'dword ptr [rsp + 0x20], r13d')], '0x412fc0', '0x413340 site2')
    return n


def check_fixed3_ir(src):
    h = va.fn_body(src, 0x412fc0)
    head = h.split('\n', 1)[0]
    assert head.count('i64 %arg') == 5 and 'i64 %arg5' in head and 'i32' not in head, 'IR 412fc0: 引数が 5 本の i64 でない: %r' % head
    assert 'load i32, ptr inttoptr (i64 %d to ptr)' % DEFAULT_IR in h, 'IR 412fc0: 既定値 global (%d) の読出しが無い' % DEFAULT_IR
    assert len(re.findall(r'\bselect i1 %p5z\b', h)) == 1, 'IR 412fc0: 5 番目の既定値分岐 (select) が 1 件でない'
    calls = re.findall(r'call i64 @function_41c8c0\(([^)]*)\)', h)
    assert calls == ['i64 %cp, i64 0, i64 %arg3, i64 %arg4, i64 %arg1, i64 %arg2, i64 0, i64 0'], 'IR 412fc0: 41c8c0 の呼出し引数が想定と違う: %r' % calls
    b = va.fn_body(src, 0x413340)
    calls_b = re.findall(r'call i64 @function_412fc0\(([^)]*)\)', b)
    assert calls_b == ['i64 0, i64 0, i64 %arg2, i64 %r9a, i64 %14',
                       'i64 %ldfx3326a, i64 %16, i64 %arg2, i64 %r9b, i64 %14'], 'IR 413340: 412fc0 の呼出し引数が想定と違う: %r' % calls_b
    all_calls = re.findall(r'call i64 @function_412fc0\(([^)]*)\)', src)
    assert len(all_calls) == 3 and all(c.count('i64 ') == 5 for c in all_calls), 'IR: 412fc0 の呼出しが 3 件・5 引数でない: %r' % all_calls
    return 6


def apply(src):
    for old, new, cnt in REPL:
        got = src.count(old)
        assert got == cnt, '[fix_abi_3451] 行が %d 件 (想定 %d): %r' % (got, cnt, old[:80])
        src = src.replace(old, new)
    return src


def negctl(fixed, m):
    bad = 0
    cases = []
    cases.append(('NC1 413340 site2 の 5 番目を 3 番目に戻す (取り違え)',
                  fixed.replace('i64 %ldfx3326a, i64 %16, i64 %arg2, i64 %r9b, i64 %14)', 'i64 %ldfx3326a, i64 %16, i64 %arg2, i64 %r9b, i64 %18)', 1)))
    cases.append(('NC2 412fc0 の既定値 global の番地を改変',
                  fixed.replace('  %dflt = load i32, ptr inttoptr (i64 18770472 to ptr), align 4\n',
                                '  %dflt = load i32, ptr inttoptr (i64 18770480 to ptr), align 4\n', 1)))
    cases.append(('NC3 412fc0 の 5 番目分岐を除去 (cp = arg5 を直接使う)',
                  fixed.replace('  %cp32 = select i1 %p5z, i32 %dflt, i32 %p5\n', '  %cp32 = add i32 %p5, 0\n', 1)))
    cases.append(('NC4 site1 の r9 を zext(arg4) に改変',
                  fixed.replace('i64 0, i64 0, i64 %arg2, i64 %r9a, i64 %14)', 'i64 0, i64 0, i64 %arg2, i64 %arg4, i64 %14)', 1)))
    for name, s in cases:
        assert s != fixed, name + ': 置換が効いていない'
        try:
            check_fixed3_ir(s)
        except AssertionError as e:
            print('[fix_abi_3451] %s: 拒否 OK (%s)' % (name, str(e)[:100]))
        else:
            print('[fix_abi_3451] %s: 拒否されなかった (NG)' % name)
            bad += 1
    pm = va._Patched(m, 0x413383 - 0x400000, bytes([0x41, 0x89, 0xF1]))  # mov r9d,ebx -> mov r9d,esi
    try:
        check_fixed3_machine(pm)
    except AssertionError as e:
        print('[fix_abi_3451] NC5 機械語 0x413383 の r9 を esi に改変 (gate): 拒否 OK (%s)' % str(e)[:100])
    else:
        print('[fix_abi_3451] NC5 機械語 0x413383 の r9 を esi に改変 (gate): 拒否されなかった (NG)')
        bad += 1
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--negctl', action='store_true')
    a = ap.parse_args()
    m = Machine(a.pe)
    src = open(a.src, errors='replace').read()
    n = check_fixed3_machine(m)
    print('[fix_abi_3451] 機械照合 OK: %d 項目 (412fc0 の 5 引数形・0x413340 の 2 site)' % n)
    fixed = apply(src)
    check_fixed3_ir(fixed)
    if a.negctl:
        bad = negctl(fixed, m)
        print('[fix_abi_3451] ネガティブコントロール: NG %d 件' % bad)
        sys.exit(1 if bad else 0)
    with open(a.dst, 'w') as f:
        f.write(fixed)
    print('[fix_abi_3451] 修復 OK: 412fc0 を 5 引数化・既定値分岐・呼出元 3 site を接続 (%s)' % a.dst)


if __name__ == '__main__':
    main()
