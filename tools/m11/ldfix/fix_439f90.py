#!/usr/bin/env python3
"""fix_439f90.py — #5693 (CI-235): function_439f90 の IR を機械語 (0x439f90〜0x43a177) どおりに組み直す。

lift 段 (RetDec drc) の IR は機械語と次の点で違う (#5688 の調査・REPORT は tools/m11/ldfix/REPORT_5693.md):
  (1) arg2 はセル (ポインタを収める場所) で、`[rbx]` の load を値として扱っていない
  (2) 0x439fe2 のループ更新 (`add r13d,1`・`word [rax]==si` 判定・`[rbx]` の更新) が無い
  (3) 0x43a094〜0x43a12f の分岐 (r13 != 1 の経路。414ad0・414850・44ba40・409c80 の呼出し) が無い
結果、0x44ba40 の呼出しは機械 4 件に対して IR は 2 件になる (mismatch_5436 の IR_FEWER)。

本 pass は関数全体を機械語の基本ブロックごとに組み直した IR に置換する。
想定と違う入力 (仮引数の署名・旧 IR の 44ba40 呼出し件数・block 構成・二重適用) は assert で止める (fail-closed)。
使い方: python3 fix_439f90.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_439f90\(.*?\n}\n', re.M | re.S)
DEF = re.compile(r'^define [^\n]*@function_439f90\(([^)]*)\)', re.M)

NEW = '''define i64 @function_439f90(ptr %arg1, ptr %arg2, i64 %arg3) local_unnamed_addr {
dec_label_pc_439f90:
  %r13.slot = alloca i64
  %rdi.slot = alloca i64
  %r14.slot = alloca i64
  %0 = ptrtoint ptr %arg2 to i64
  %1 = ptrtoint ptr %arg1 to i64
  %2 = call i64 @function_412d60(i64 %1, i64 %0)
  %si = trunc i64 %arg3 to i16
  %c0 = load i64, ptr %arg2, align 8
  %c0z = icmp eq i64 %c0, 0
  br i1 %c0z, label %dec_label_pc_43a167, label %dec_label_pc_439fba

dec_label_pc_439fba:
  %p0 = inttoptr i64 %c0 to ptr
  %w0 = load i16, ptr %p0, align 2
  %m0 = icmp eq i16 %w0, %si
  br i1 %m0, label %dec_label_pc_439fc6, label %dec_label_pc_43a167

dec_label_pc_439fc6:
  %c1 = load i64, ptr %arg2, align 8
  %c2 = add i64 %c1, 2
  store i64 %c2, ptr %arg2, align 8
  store i64 1, ptr %r13.slot, align 8
  %rdi0 = load i64, ptr %arg2, align 8
  store i64 %rdi0, ptr %rdi.slot, align 8
  %n0 = call i64 @function_44ba40(i64 %rdi0, i16 %si)
  store i64 %n0, ptr %arg2, align 8
  br label %dec_label_pc_43a003

dec_label_pc_439fe2:
  %c3 = load i64, ptr %arg2, align 8
  %c4 = add i64 %c3, 2
  store i64 %c4, ptr %arg2, align 8
  %p4 = inttoptr i64 %c4 to ptr
  %w4 = load i16, ptr %p4, align 2
  %m4 = icmp eq i16 %w4, %si
  br i1 %m4, label %dec_label_pc_439fee, label %dec_label_pc_43a009

dec_label_pc_439fee:
  %c5 = load i64, ptr %arg2, align 8
  %c6 = add i64 %c5, 2
  store i64 %c6, ptr %arg2, align 8
  %r13a = load i64, ptr %r13.slot, align 8
  %r13b = add i64 %r13a, 1
  store i64 %r13b, ptr %r13.slot, align 8
  %c7 = load i64, ptr %arg2, align 8
  %n4 = call i64 @function_44ba40(i64 %c7, i16 %si)
  store i64 %n4, ptr %arg2, align 8
  br label %dec_label_pc_43a003

dec_label_pc_43a003:
  %c8 = load i64, ptr %arg2, align 8
  %c8z = icmp eq i64 %c8, 0
  br i1 %c8z, label %dec_label_pc_43a009, label %dec_label_pc_439fe2

dec_label_pc_43a009:
  %c9 = load i64, ptr %arg2, align 8
  %c9z = icmp eq i64 %c9, 0
  %r14v = zext i1 %c9z to i64
  store i64 %r14v, ptr %r14.slot, align 8
  br i1 %c9z, label %dec_label_pc_43a00c, label %dec_label_pc_43a027

dec_label_pc_43a00c:
  %rdi1 = load i64, ptr %rdi.slot, align 8
  %c10 = call i64 @function_43d5c0(i64 %rdi1)
  store i64 %c10, ptr %arg2, align 8
  br label %dec_label_pc_43a027

dec_label_pc_43a027:
  %rdi2 = load i64, ptr %rdi.slot, align 8
  %c11 = load i64, ptr %arg2, align 8
  %d11 = sub i64 %c11, %rdi2
  %h = sdiv i64 %d11, 2
  %r14c = load i64, ptr %r14.slot, align 8
  %t1 = add i64 %h, %r14c
  %t1b = sub i64 %t1, 1
  %t1z = icmp sle i64 %t1b, 0
  br i1 %t1z, label %dec_label_pc_43a167, label %dec_label_pc_43a04b

dec_label_pc_43a04b:
  %r13c = load i64, ptr %r13.slot, align 8
  %r13w = trunc i64 %r13c to i32
  %r13s = sext i32 %r13w to i64
  %t2 = sub i64 %h, %r13s
  %t3 = add i64 %t2, %r14c
  %t3z = icmp sle i64 %t3, 0
  br i1 %t3z, label %dec_label_pc_43a167, label %dec_label_pc_43a06a

dec_label_pc_43a06a:
  %r13e = icmp eq i32 %r13w, 1
  br i1 %r13e, label %dec_label_pc_43a070, label %dec_label_pc_43a094

dec_label_pc_43a070:
  %rdi3 = load i64, ptr %rdi.slot, align 8
  %rdi3p = inttoptr i64 %rdi3 to ptr
  %r8a = add i64 %h, %r14c
  %r8b = sub i64 %r8a, 1
  %c413060 = call i64 @function_413060(i64 %1, ptr %rdi3p, i64 %r8b)
  br label %dec_label_pc_43a167

dec_label_pc_43a094:
  %r13f = load i64, ptr %r13.slot, align 8
  %r13g = trunc i64 %r13f to i32
  %r13h = sext i32 %r13g to i64
  %t4 = sub i64 %h, %r13h
  %t5 = add i64 %t4, %r14c
  %t5w = trunc i64 %t5 to i32
  %t5z = zext i32 %t5w to i64
  %c414ad0 = call i64 @function_414ad0(i64 %1, i64 %t5z)
  %a0 = load i64, ptr %arg1, align 8
  %r13new = call i64 @function_414850(i64 %a0)
  store i64 %r13new, ptr %r13.slot, align 8
  %rdi4 = load i64, ptr %rdi.slot, align 8
  %n6 = call i64 @function_44ba40(i64 %rdi4, i16 %si)
  store i64 %n6, ptr %arg2, align 8
  br label %dec_label_pc_43a129

dec_label_pc_43a0d5:
  %c12 = load i64, ptr %arg2, align 8
  %c13 = add i64 %c12, 2
  store i64 %c13, ptr %arg2, align 8
  %p13 = inttoptr i64 %c13 to ptr
  %w13 = load i16, ptr %p13, align 2
  %m13 = icmp eq i16 %w13, %si
  br i1 %m13, label %dec_label_pc_43a0e1, label %dec_label_pc_43a12f

dec_label_pc_43a0e1:
  %rdi5 = load i64, ptr %rdi.slot, align 8
  %r13i = load i64, ptr %r13.slot, align 8
  %c14 = load i64, ptr %arg2, align 8
  %d14 = sub i64 %c14, %rdi5
  %s14 = sdiv i64 %d14, 2
  %r8c = mul i64 %s14, 2
  %c409c80a = call i64 @function_409c80(i64 %rdi5, i64 %r13i, i64 %r8c)
  %c15 = load i64, ptr %arg2, align 8
  %d15 = sub i64 %c15, %rdi5
  %s15 = sdiv i64 %d15, 2
  %s15b = mul i64 %s15, 2
  %r13j = add i64 %r13i, %s15b
  store i64 %r13j, ptr %r13.slot, align 8
  %c16 = load i64, ptr %arg2, align 8
  %c17 = add i64 %c16, 2
  store i64 %c17, ptr %arg2, align 8
  %rdi6 = load i64, ptr %arg2, align 8
  store i64 %rdi6, ptr %rdi.slot, align 8
  %n7 = call i64 @function_44ba40(i64 %rdi6, i16 %si)
  store i64 %n7, ptr %arg2, align 8
  br label %dec_label_pc_43a129

dec_label_pc_43a129:
  %c18 = load i64, ptr %arg2, align 8
  %c18z = icmp eq i64 %c18, 0
  br i1 %c18z, label %dec_label_pc_43a12f, label %dec_label_pc_43a0d5

dec_label_pc_43a12f:
  %c19 = load i64, ptr %arg2, align 8
  %c19z = icmp eq i64 %c19, 0
  br i1 %c19z, label %dec_label_pc_43a136, label %dec_label_pc_43a141

dec_label_pc_43a136:
  %rdi7 = load i64, ptr %rdi.slot, align 8
  %c20 = call i64 @function_43d5c0(i64 %rdi7)
  store i64 %c20, ptr %arg2, align 8
  br label %dec_label_pc_43a141

dec_label_pc_43a141:
  %rdi8 = load i64, ptr %rdi.slot, align 8
  %r13k = load i64, ptr %r13.slot, align 8
  %c21 = load i64, ptr %arg2, align 8
  %d21 = sub i64 %c21, %rdi8
  %s21 = sdiv i64 %d21, 2
  %r14d = load i64, ptr %r14.slot, align 8
  %r8d = add i64 %s21, %r14d
  %r8e = sub i64 %r8d, 1
  %r8f = mul i64 %r8e, 2
  %c409c80b = call i64 @function_409c80(i64 %rdi8, i64 %r13k, i64 %r8f)
  br label %dec_label_pc_43a167

dec_label_pc_43a167:
  ret i64 %1
}
'''


def patch(fn):
    d = DEF.match(fn)
    assert d, 'function_439f90 の define 行が読めない'
    assert d.group(1).replace(' ', '') == 'ptr%arg1,ptr%arg2,i64%arg3', '仮引数の署名が想定と違う: %r' % d.group(1)
    assert fn.count('call i64 @function_44ba40(') == 2, '旧 IR の 44ba40 呼出しが 2 件でない (適用済みか想定外): %d' % fn.count('call i64 @function_44ba40(')
    assert 'dec_label_pc_43a027:' in fn and 'dec_label_pc_43a07f:' in fn, '旧 IR の block 構成が想定と違う'
    assert 'dec_label_pc_43a094' not in fn, '適用済み (二重適用)'
    return NEW


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_439f90 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_439f90] function_439f90: 機械語どおりの IR に置換 (arg2 セルの load・r13 ループ更新・r13!=1 分岐を復元)')


if __name__ == '__main__':
    main()
