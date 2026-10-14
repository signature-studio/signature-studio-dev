#!/usr/bin/env python3
"""fix_450560.py — #2502 (CI-100): function_450560 の 2 段 deref 脱落を直す (#942 受入 2・#1282 と同類型)。

機械語 (PE VA 0x450560・.text) は、第 1 引数 arg1 (src の `**`) と第 2 引数 arg2 (dest の `**`) をスピル
([rsp+0x60]=rcx=arg1, [rsp+0x68]=rdx=arg2) したあと、`mov rax,[rsp+0x60]; mov rdx,[rax]` で
`*arg1` を読んで `UStrAsg(arg2, *arg1)` を呼ぶ。以降も `*arg1` / `*arg2` を読む箇所 (cmp・dword[rax-4]・
414850 の引数) は全て 1 段 deref (値を読んでからアドレスとして使う)。
base IR (lift 段) は `*arg1` `*arg2` の読出しを落とし、アドレス (arg1 / arg2) そのものを値として渡していた:
  `call 4133f0(arg2, arg2)` / `icmp eq arg2, 0` / `load i32 (arg2-4)` / `414850(arg2)` の 2 件。
本 pass は関数本体を機械語に合わせた IR に置き換える。修正箇所は lift 段ではなく IR 修復 pass (本ファイル)。
理由: 落ちた段は RetDec の「スピルした引数経由の 2 段目 load」で、既存 ldfix の F1〜F4 のどれにも当たらない。
`test rax,rax; je` の nil ガード (dword[rax-4] の前) も base IR に無いため、分岐を含めて書き直す。

機械検証: 上の機械語が想定どおり (mnemonic と operand 文字列) であることを capstone で確認し、
一致しなければ assert で止める (fail-closed)。IR 側も base 形 (`call 4133f0(arg2, arg2)` が 1 件) のときだけ書き換える。
LCMapStringW の第 6 引数 (cchDest) は機械語の [rsp+0x28] (= edi = dword[*arg2-4]) に合わせる。
44cb40 の引数は機械語で未設定 (rcx/rdx は LCMapStringW 後の残骸) のため base の値を据え置く (未検証)。

使い方: python3 fix_450560.py IN.ll OUT.ll --pe PE.bin
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ldmach import Machine  # noqa: E402

VA = 0x450560
FN = re.compile(r'^define [^\n]*@function_450560\(.*?\n}\n', re.M | re.S)
BROKEN = 'call i64 @function_4133f0(i64 %arg2, i64 %arg2)'

# 機械語で検証する命令 (VA, mnemonic, op_str)。capstone の出力文字列と完全一致させる
EXPECT = [
    (0x450576, 'mov', 'rcx, qword ptr [rsp + 0x68]'),
    (0x45057b, 'mov', 'rax, qword ptr [rsp + 0x60]'),
    (0x450580, 'mov', 'rdx, qword ptr [rax]'),
    (0x450583, 'call', '0x4133f0'),
    (0x450588, 'mov', 'rax, qword ptr [rsp + 0x68]'),
    (0x45058d, 'cmp', 'qword ptr [rax], 0'),
    (0x450598, 'call', '0x413780'),
    (0x45059f, 'mov', 'rax, qword ptr [rsp + 0x60]'),
    (0x4505a4, 'mov', 'rax, qword ptr [rax]'),
    (0x4505ac, 'mov', 'esi, dword ptr [rax - 4]'),
    (0x4505af, 'xor', 'edi, edi'),
    (0x4505b1, 'mov', 'rax, qword ptr [rsp + 0x68]'),
    (0x4505b6, 'mov', 'rax, qword ptr [rax]'),
    (0x4505be, 'mov', 'edi, dword ptr [rax - 4]'),
    (0x4505c9, 'call', '0x414850'),
    (0x4505d9, 'call', '0x414850'),
    (0x4505f4, 'call', '0x423970'),
    (0x4505fd, 'call', '0x44cb40'),
]

NEW_BODY = '''dec_label_pc_450560:
  %p1 = inttoptr i64 %arg1 to ptr
  %v1 = load i64, ptr %p1, align 8
  %0 = call i64 @function_4133f0(i64 %arg2, i64 %v1)
  %p2 = inttoptr i64 %arg2 to ptr
  %v2 = load i64, ptr %p2, align 8
  %1 = icmp eq i64 %v2, 0
  br i1 %1, label %dec_label_pc_450602, label %dec_label_pc_450593

dec_label_pc_450593:                              ; preds = %dec_label_pc_450560
  %2 = call i64 @function_413780(i64 %arg2)
  %p1b = inttoptr i64 %arg1 to ptr
  %v1b = load i64, ptr %p1b, align 8
  %z1 = icmp eq i64 %v1b, 0
  br i1 %z1, label %dec_label_pc_4505af, label %dec_label_pc_4505ac

dec_label_pc_4505ac:
  %s1 = add i64 %v1b, -4
  %s2 = inttoptr i64 %s1 to ptr
  %s3 = load i32, ptr %s2, align 4
  br label %dec_label_pc_4505af

dec_label_pc_4505af:
  %esi = phi i32 [ 0, %dec_label_pc_450593 ], [ %s3, %dec_label_pc_4505ac ]
  %p2b = inttoptr i64 %arg2 to ptr
  %v2b = load i64, ptr %p2b, align 8
  %z2 = icmp eq i64 %v2b, 0
  br i1 %z2, label %dec_label_pc_4505c1, label %dec_label_pc_4505be

dec_label_pc_4505be:
  %t1 = add i64 %v2b, -4
  %t2 = inttoptr i64 %t1 to ptr
  %t3 = load i32, ptr %t2, align 4
  br label %dec_label_pc_4505c1

dec_label_pc_4505c1:
  %edi = phi i32 [ 0, %dec_label_pc_4505af ], [ %t3, %dec_label_pc_4505be ]
  %p1c = inttoptr i64 %arg1 to ptr
  %v1c = load i64, ptr %p1c, align 8
  %3 = call i64 @function_414850(i64 %v1c)
  %p2c = inttoptr i64 %arg2 to ptr
  %v2c = load i64, ptr %p2c, align 8
  %4 = call i64 @function_414850(i64 %v2c)
  %5 = inttoptr i64 %3 to ptr
  %6 = inttoptr i64 %4 to ptr
  %7 = call i32 @LCMapStringW(i32 %arg3, i32 16777472, ptr %5, i32 %esi, ptr %6, i32 %edi)
  %8 = icmp eq i32 %7, 0
  br i1 %8, label %dec_label_pc_4505fd, label %dec_label_pc_450602

dec_label_pc_4505fd:                              ; preds = %dec_label_pc_4505c1
  %9 = zext i32 %arg3 to i64
  %10 = call i64 @function_44cb40(i64 %9, i64 16777472)
  br label %dec_label_pc_450602

dec_label_pc_450602:
  ret i64 %arg2

}
'''


def verify_machine(pe):
    m = Machine(pe)
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = m.read(VA - 0x400000, 0x120)
    got = {i.address: (i.mnemonic, i.op_str) for i in cs.disasm(code, VA)}
    for addr, mn, ops in EXPECT:
        assert addr in got, '機械語 0x%x が逆アセンブルできない' % addr
        assert got[addr] == (mn, ops), '機械語 0x%x が想定と違う: %r != %r' % (addr, got[addr], (mn, ops))
    return len(EXPECT)


def patch(fn):
    head, _, _ = fn.partition('\n')
    assert '@function_450560(' in head and head.startswith('define '), 'define 行が読めない'
    assert fn.count(BROKEN) == 1, 'base 形 (%s が 1 件) でない: 適用済み or 想定外の IR' % BROKEN
    assert 'dec_label_pc_450560:' in fn, 'エントリブロックが無い'
    return head + '\n' + NEW_BODY


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    n = verify_machine(a.pe)
    src = open(a.src, errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_450560 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(a.dst, 'w').write(out)
    print('[fix_450560] 機械語 %d 命令を検証 (VA 0x450560)。function_450560 本体を 2 段 deref 復元形に置換' % n)


if __name__ == '__main__':
    main()
