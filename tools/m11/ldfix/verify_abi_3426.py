#!/usr/bin/env python3
"""verify_abi_3426.py — #3426 (CI-157): 0x412fc0 と呼出先 0x41c8c0 の呼出規約を機械語 (capstone) と IR で照合する。

IR は変更しない (検査のみ)。照合が 1 件でも外れたら assert で止める (fail-closed)。
  機械語 (正本): 0x412fc0 は 5 番目引数 ([rsp+0x70] = 入口 [rsp+0x28]) を読み、0 のとき既定値の global を使い、
                 rcx = その値 (zero-ext)・rdx = 0・r8/r9 は素通し、スタック [rsp+0x20..0x38] = arg1, arg2, 0, 0 で
                 0x41c8c0 を呼ぶ。0x41c8c0 は 5〜8 番目の引数をスタックから読んで 0x4070e0 (IAT thunk) へ転送する。
  IR (現状):     function_412fc0 は 3 引数・分岐なし・call 1 件 (sext arg1, sext arg2, 0, 0)。
                 function_41c8c0 は 4 引数 (= 機械語の 5〜8 番目) で、レジスタ由来の値は `xor i64 0, 0` に化けている。

使い方:
  python3 verify_abi_3426.py IR.ll --pe PE.bin              # 照合 (不一致で exit 1)
  python3 verify_abi_3426.py IR.ll --pe PE.bin --negctl     # ネガティブコントロール (全件拒否されること)
"""
import argparse
import copy
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ldmach import Machine  # noqa: E402
import capstone  # noqa: E402

DEFAULT_GLOBAL_VA = 0x15e6a28  # 0x412fcb の mov eax,[rip+disp] の参照先 (既定値の global)

FN_A = 0x412fc0  # 呼出し元 (3 引数の IR しか無い)
FN_B = 0x41c8c0  # 呼出先 (IR は 4 引数)
THUNK = 0x4070e0

MACHINE_A = [
    (0x412fc0, 'sub', 'rsp, 0x48'),
    (0x412fc4, 'cmp', 'dword ptr [rsp + 0x70], 0'),
    (0x412fc9, 'jne', '0x412fd5'),
    (0x412fcb, 'mov', 'eax, dword ptr [rip + 0x11d3a57]'),
    (0x412fd1, 'mov', 'dword ptr [rsp + 0x70], eax'),
    (0x412fd5, 'mov', 'eax, dword ptr [rsp + 0x70]'),
    (0x412fd9, 'xor', 'r10, r10'),
    (0x412fdc, 'mov', 'qword ptr [rsp + 0x20], rcx'),
    (0x412fe1, 'mov', 'dword ptr [rsp + 0x28], edx'),
    (0x412fe5, 'mov', 'qword ptr [rsp + 0x30], 0'),
    (0x412fee, 'mov', 'qword ptr [rsp + 0x38], 0'),
    (0x412ff7, 'mov', 'ecx, eax'),
    (0x412ff9, 'mov', 'edx, r10d'),
    (0x412ffc, 'call', '0x41c8c0'),
]

MACHINE_B = [
    (0x41c8c0, 'sub', 'rsp, 0x48'),
    (0x41c8c4, 'mov', 'rax, qword ptr [rsp + 0x70]'),
    (0x41c8c9, 'mov', 'qword ptr [rsp + 0x20], rax'),
    (0x41c8ce, 'mov', 'eax, dword ptr [rsp + 0x78]'),
    (0x41c8d2, 'mov', 'dword ptr [rsp + 0x28], eax'),
    (0x41c8d6, 'mov', 'rax, qword ptr [rsp + 0x80]'),
    (0x41c8de, 'mov', 'qword ptr [rsp + 0x30], rax'),
    (0x41c8e3, 'mov', 'rax, qword ptr [rsp + 0x88]'),
    (0x41c8eb, 'mov', 'qword ptr [rsp + 0x38], rax'),
    (0x41c8f0, 'call', '0x4070e0'),
]


def disasm(m, fn, n):
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.detail = True
    code = m.read(fn - 0x400000, n)
    return list(cs.disasm(code, fn))


def verify_machine(m, fn, expect, name):
    ins = disasm(m, fn, expect[-1][0] - fn + 16)
    got = {i.address: i for i in ins}
    for addr, mn, ops in expect:
        assert addr in got, '%s: 機械語 0x%x が逆アセンブルできない' % (name, addr)
        i = got[addr]
        assert (i.mnemonic, i.op_str) == (mn, ops), '%s: 0x%x が想定と違う: %r != %r' % (name, addr, (i.mnemonic, i.op_str), (mn, ops))
    return len(expect)


def verify_default_global(m):
    """0x412fcb の rip 相対参照先が既定値 global (DEFAULT_GLOBAL_VA) であること"""
    ins = {i.address: i for i in disasm(m, FN_A, 0x20)}
    i = ins[0x412fcb]
    mem = [o for o in i.operands if o.type == capstone.x86.X86_OP_MEM][0]
    assert mem.mem.base == capstone.x86.X86_REG_RIP, '0x412fcb: rip 相対でない'
    target = i.address + i.size + mem.mem.disp
    assert target == DEFAULT_GLOBAL_VA, '0x412fcb: 既定値 global の参照先が 0x%x (想定 0x%x)' % (target, DEFAULT_GLOBAL_VA)
    return 1


def verify_thunk(m):
    ins = disasm(m, THUNK, 8)
    assert ins and ins[0].mnemonic == 'jmp' and 'qword ptr [rip +' in ins[0].op_str, '0x4070e0 が IAT thunk (jmp [rip+x]) でない: %r' % (ins[0].op_str if ins else None)
    return 1


def fn_body(src, fn):
    fns = list(re.finditer(r'^define [^\n]*@function_%x\(.*?\n}\n' % fn, src, re.M | re.S))
    assert len(fns) == 1, 'IR: function_%x の定義が 1 件でない: %d' % (fn, len(fns))
    return fns[0].group(0)


def verify_ir(src):
    a = fn_body(src, FN_A)
    head = a.split('\n', 1)[0]
    assert head.count(',') == 2 and head.count('i32 ') == 2 and 'i64 %arg3' in head, 'IR 412fc0: 引数が (i32, i32, i64) でない: %r' % head
    assert not re.search(r'\b(br|icmp|select)\b', a), 'IR 412fc0: 分岐 (5 番目引数の既定値) が既に入っている'
    calls = re.findall(r'call i64 @function_41c8c0\(([^)]*)\)', a)
    assert calls == ['i64 %0, i64 %1, i64 0, i64 0'], 'IR 412fc0: 41c8c0 への呼出し引数が想定と違う: %r' % calls
    b = fn_body(src, FN_B)
    head_b = b.split('\n', 1)[0]
    assert head_b.count('i64 %arg') == 4 and 'i64 %arg5' not in head_b, 'IR 41c8c0: 引数が 4 本でない: %r' % head_b
    assert len(re.findall(r'= xor i64 0, 0', b)) == 4, 'IR 41c8c0: レジスタ由来の xor 0 が 4 本でない'
    assert len(re.findall(r'call i32 @WideCharToMultiByte\(', b)) == 1, 'IR 41c8c0: WideCharToMultiByte 呼出しが 1 件でない'
    return 6


def check(src, m, machine_a=MACHINE_A, machine_b=MACHINE_B, default_va=None):
    global DEFAULT_GLOBAL_VA
    old = DEFAULT_GLOBAL_VA
    if default_va is not None:
        DEFAULT_GLOBAL_VA = default_va
    try:
        n = verify_machine(m, FN_A, machine_a, '0x412fc0')
        n += verify_default_global(m)
        n += verify_machine(m, FN_B, machine_b, '0x41c8c0')
        n += verify_thunk(m)
    finally:
        DEFAULT_GLOBAL_VA = old
    n += verify_ir(src)
    return n


def negctl(src, m):
    cases = []
    a2 = copy.deepcopy(MACHINE_A)
    a2[8] = (0x412fe1, 'mov', 'dword ptr [rsp + 0x30], edx')
    cases.append(('NC1 412fc0 の 2 番目スタック引数の位置 (0x28 → 0x30)', dict(machine_a=a2)))
    a3 = copy.deepcopy(MACHINE_A)
    a3[2] = (0x412fc9, 'je', '0x412fd5')
    cases.append(('NC2 412fc0 の分岐の向き (jne → je)', dict(machine_a=a3)))
    cases.append(('NC3 既定値 global の参照先の改変', dict(default_va=DEFAULT_GLOBAL_VA + 8)))
    b2 = copy.deepcopy(MACHINE_B)
    b2[9] = (0x41c8f0, 'call', '0x4070e8')
    cases.append(('NC4 41c8c0 の呼出先の改変', dict(machine_b=b2)))
    bad = 0
    for name, kw in cases:
        try:
            check(src, m, **kw)
        except AssertionError as e:
            print('[verify_abi_3426] %s: 拒否 OK (%s)' % (name, str(e)[:110]))
        else:
            print('[verify_abi_3426] %s: 拒否されなかった (NG)' % name)
            bad += 1
    # NC5: IR の 412fc0 に分岐を足した形 (修復後と同形) は現状の照合で拒否されること
    body = fn_body(src, FN_A)
    src5 = src.replace(body, body.replace('  %0 = sext i32 %arg1 to i64\n', '  %x = icmp eq i64 %arg3, 0\n  %0 = sext i32 %arg1 to i64\n', 1), 1)
    assert src5 != src
    try:
        check(src5, m)
    except AssertionError as e:
        print('[verify_abi_3426] NC5 IR に分岐を追加: 拒否 OK (%s)' % str(e)[:110])
    else:
        print('[verify_abi_3426] NC5 IR に分岐を追加: 拒否されなかった (NG)')
        bad += 1
    return bad


ARG_FAM = {'rcx', 'ecx', 'cx', 'cl', 'rdx', 'edx', 'dx', 'dl', 'r8', 'r8d', 'r8w', 'r8b', 'r9', 'r9d', 'r9w', 'r9b'}
CP_UTF8 = 0xfde9  # 0x41c283・0x41c325 の mov ecx,0xfde9 (CodePage = CP_UTF8 = 65001)


def insns(m, start, end):
    return [i for i in disasm(m, start, end - start + 16) if i.address < end]


def writes(i):
    return [i.reg_name(o.reg) for o in i.operands if o.type == capstone.x86.X86_OP_REG and (o.access & capstone.CS_AC_WRITE)]


def window_exact(m, start, call, expect, name):
    """start から call までが expect (VA・mnemonic・operand) と一致し、call で終わること (直線区間の完全一致)"""
    ins = disasm(m, start, call - start + 16)
    seq = []
    for i in ins:
        seq.append((i.address, i.mnemonic, i.op_str))
        if i.address == call:
            break
    want = list(expect) + [(call, 'call', '0x41c8c0')]
    assert seq == want, '%s: 呼出し直前の区間が想定と違う: %r != %r' % (name, seq, want)
    return len(want)


def no_write(m, start, end, fam, name):
    bad = [(hex(i.address), i.mnemonic, i.op_str) for i in insns(m, start, end) if set(writes(i)) & fam]
    assert not bad, '%s: 引数レジスタを書き換える命令がある: %r' % (name, bad)
    return 1


def check_fixed_machine(m):
    """#3450: 0x41c8c0 の rcx〜r9 は無改変で 0x4070e0 へ渡る。呼出元 3 site の呼出し直前の rcx〜r9 を機械語と照合する。"""
    n = no_write(m, 0x41c8c0, 0x41c8f0, ARG_FAM, '0x41c8c0')
    # 0x41c260 の 2 site: rcx=CP_UTF8・rdx=0・r8 素通し・r9=zext(edi)=素通し (edi は 0x41c26c でだけ書かれる)・スタック 5〜8
    assert [hex(i.address) for i in insns(m, 0x41c260, 0x41c352) if set(writes(i)) & {'rdi', 'edi'}] == ['0x41c26c'], 'edi の書込みが 0x41c26c だけでない'
    n += no_write(m, 0x41c260, 0x41c352, {'r8', 'r8d', 'r8w', 'r8b'}, '0x41c260 (r8)')
    n += window_exact(m, 0x41c283, 0x41c2a8, [
        (0x41c283, 'mov', 'ecx, 0x%x' % CP_UTF8), (0x41c288, 'xor', 'edx, edx'), (0x41c28a, 'mov', 'r9d, edi'),
        (0x41c28d, 'mov', 'qword ptr [rsp + 0x20], rbx'), (0x41c292, 'mov', 'dword ptr [rsp + 0x28], esi'),
        (0x41c296, 'mov', 'qword ptr [rsp + 0x30], 0'), (0x41c29f, 'mov', 'qword ptr [rsp + 0x38], 0')], '0x41c2a8 (site1)')
    n += window_exact(m, 0x41c325, 0x41c352, [
        (0x41c325, 'mov', 'ecx, 0x%x' % CP_UTF8), (0x41c32a, 'xor', 'edx, edx'), (0x41c32c, 'mov', 'r9d, edi'),
        (0x41c32f, 'mov', 'qword ptr [rsp + 0x20], 0'), (0x41c338, 'mov', 'dword ptr [rsp + 0x28], 0'),
        (0x41c340, 'mov', 'qword ptr [rsp + 0x30], 0'), (0x41c349, 'mov', 'qword ptr [rsp + 0x38], 0')], '0x41c352 (site2)')
    # 0x412fc0 の 1 site: rdx=0 (r10=0)・r8 素通し・r9 素通し。rcx は 5 番目/既定値 (IR に値が無い = 残件 CI-164)
    n += no_write(m, 0x412fc0, 0x412ffc, {'r8', 'r8d', 'r8w', 'r8b', 'r9', 'r9d', 'r9w', 'r9b'}, '0x412fc0 (r8/r9)')
    n += window_exact(m, 0x412fd5, 0x412ffc, [
        (0x412fd5, 'mov', 'eax, dword ptr [rsp + 0x70]'), (0x412fd9, 'xor', 'r10, r10'),
        (0x412fdc, 'mov', 'qword ptr [rsp + 0x20], rcx'), (0x412fe1, 'mov', 'dword ptr [rsp + 0x28], edx'),
        (0x412fe5, 'mov', 'qword ptr [rsp + 0x30], 0'), (0x412fee, 'mov', 'qword ptr [rsp + 0x38], 0'),
        (0x412ff7, 'mov', 'ecx, eax'), (0x412ff9, 'mov', 'edx, r10d')], '0x412ffc (412fc0)')
    return n


def check_fixed_ir(src):
    """#3450 修復後の IR: 41c8c0 は 8 引数、呼出しは全て 8 引数。WideCharToMultiByte の引数は rcx〜r9 と 5〜8 番目に接続する。"""
    b = fn_body(src, FN_B)
    head_b = b.split('\n', 1)[0]
    assert head_b.count('i64 %arg') == 8 and 'i64 %arg9' not in head_b, 'IR 41c8c0: 引数が 8 本でない: %r' % head_b
    assert not re.search(r'= xor i64 0, 0', b), 'IR 41c8c0: xor 0 の定数が残っている'
    assert re.findall(r'call i32 @WideCharToMultiByte\((.*?)\)\n', b) == [
        'i32 %6, i32 %7, ptr %8, i32 %9, ptr %10, i32 %5, ptr %11, ptr %12'], 'IR 41c8c0: WideCharToMultiByte の引数が想定と違う'
    calls = re.findall(r'call i64 @function_41c8c0\(([^)]*)\)', src)
    assert len(calls) == 4 and all(c.count('i64 ') == 8 for c in calls), 'IR: 41c8c0 の呼出しが 4 件・8 引数でない: %r' % calls
    return 4


def check_fixed(src, m):
    return check_fixed_machine(m) + check_fixed_ir(src)


def passthrough_violations(code):
    """negctl 用: 任意の機械語列 (VA 0x41c8c0 起点) で rcx〜r9 を書く命令を数える"""
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.detail = True
    return [i for i in cs.disasm(code, FN_B) if set(writes(i)) & ARG_FAM]


def negctl_fixed(src, m):
    bad = 0
    cases = []
    # NC6: 0x41c8c0 の先頭に rcx を書く命令を足す (機械語の rcx 転送の改変)
    real = m.read(FN_B - 0x400000, 0x30)
    v = passthrough_violations(bytes([0x31, 0xc9]) + real)
    cases.append(('NC6 0x41c8c0 の先頭に xor ecx,ecx (rcx 転送の改変)', len(v) > 0))
    # NC7: 呼出元の 1 つを 4 引数に戻す (呼出元の引数数の不一致)
    old7 = 'call i64 @function_41c8c0(i64 65001, i64 0, i64 %arg3, i64 %arg4, i64 %arg1, i64 %2, i64 0, i64 0)'
    src7 = src.replace(old7, 'call i64 @function_41c8c0(i64 %arg1, i64 %2, i64 0, i64 0)', 1)
    cases.append(('NC7 41c260 の呼出元 1 site を 4 引数に戻す', src7 != src and _rejects(check_fixed_ir, src7)))
    for name, ok in cases:
        if ok:
            print('[verify_abi_3426] %s: 拒否 OK' % name)
        else:
            print('[verify_abi_3426] %s: 拒否されなかった (NG)' % name)
            bad += 1
    return bad


def _rejects(fn, *a):
    try:
        fn(*a)
    except AssertionError:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--negctl', action='store_true')
    ap.add_argument('--fixed', action='store_true', help='修復後 IR (#3450) を照合する。既定は修復前 IR (#3426)')
    a = ap.parse_args()
    m = Machine(a.pe)
    src = open(a.ir, errors='replace').read()
    if a.fixed:
        if a.negctl:
            bad = negctl_fixed(src, m)
            print('[verify_abi_3426] ネガティブコントロール (修復後): NG %d 件' % bad)
            sys.exit(1 if bad else 0)
        n = check_fixed(src, m)
        print('[verify_abi_3426] 照合 OK (修復後): 機械語・IR で %d 項目 (0x41c8c0 の 8 引数化と呼出元 4 site)' % n)
        return
    if a.negctl:
        bad = negctl(src, m)
        print('[verify_abi_3426] ネガティブコントロール: NG %d 件' % bad)
        sys.exit(1 if bad else 0)
    n = check(src, m)
    print('[verify_abi_3426] 照合 OK: 機械語 %d 命令 + IR 6 項目 (0x412fc0 → 0x41c8c0 の呼出規約)' % n)


if __name__ == '__main__':
    main()
