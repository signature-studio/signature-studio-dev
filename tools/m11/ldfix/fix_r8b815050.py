#!/usr/bin/env python3
"""fix_r8b815050.py — #1448 (#683 §8.1): function_815050 の `call function_6cefb0` の第 3 引数を機械語の即値 1 に直す。

機械語 8158f5〜8158f8: `mov r8b, 1` → `call 0x6cefb0` (第 3 引数 = r8 の下位 8bit が 1)。
r8 は直前の `lea r8,[rbp+0x1c8]` (81550a) の後に call が挟まる。Win64 では r8 は呼出しで壊れるので、上位 56bit は
不定と読める。RetDec 段がこの値をどう合成して alloca アドレスにしたか (pass 特定) は未確認 (推定)。
callee function_6cefb0 の第 3 引数の使い方は IR で 2 箇所 (`icmp slt i64 %0, %29` と `trunc i64 %0 to i8`) だけ。
機械語側も `cmp byte ptr [rcx+0x496], r8b` (8bit 比較) しかない。よって値 1 の ptr (`inttoptr (i64 1 to ptr)`) が
機械語の振る舞いと一致する。alloca 本体は残す (未使用の死んだ slot になる)。
これは因果の確認ではない。修復後も unit 280/659 は callee 内で OOB のまま (REPORT_683.md §8.1)。

機械語の前提 (8158f5 が `mov r8b, 1`、8158f8 が `call 0x6cefb0`、6cf021 が `cmp byte ptr [rcx+0x496], r8b`) を
capstone で確認し、崩れていたら assert で止める (fail-closed)。IR の想定 (呼出しが 1 件・alloca の使用が 2 箇所だけ・
二重適用なし) も同様に assert する。

使い方: python3 fix_r8b815050.py IN.ll OUT.ll --pe PE
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FN = re.compile(r'^define [^\n]*@function_815050\(.*?\n}\n', re.M | re.S)
CALL = re.compile(r'call i64 @function_6cefb0\(i64 (%\w+), i64 (%\w+), ptr nonnull %stack_var_-255\)')
ALLOCA = '%stack_var_-255 = alloca i64, align 8\n'
NEW = 'call i64 @function_6cefb0(i64 \\1, i64 \\2, ptr inttoptr (i64 1 to ptr))'


def check_machine(pe):
    import ldmach
    m = ldmach.Machine(pe)
    ins = {i.address: i for i in m.disasm_fn(0x815050) or []}
    a = ins.get(0x8158f5)
    assert a and a.mnemonic == 'mov' and a.op_str == 'r8b, 1', '8158f5 が mov r8b, 1 でない: %s' % (a and a.op_str)
    b = ins.get(0x8158f8)
    assert b and b.mnemonic == 'call' and b.op_str == '0x6cefb0', '8158f8 が call 0x6cefb0 でない'
    c = {i.address: i for i in m.disasm_fn(0x6cefb0) or []}
    d = c.get(0x6cf021)
    assert d and d.mnemonic == 'cmp' and d.op_str == 'byte ptr [rcx + 0x496], r8b', '6cf021 が byte 比較でない: %s' % (d and d.op_str)


def patch(fn):
    assert fn.count('@function_6cefb0(') == 1, 'function_815050 の 6cefb0 呼出しが 1 件でない'
    assert fn.count(ALLOCA) == 1, 'alloca %stack_var_-255 の宣言が 1 件でない'
    assert fn.count('%stack_var_-255') == 2, 'alloca の使用が宣言と呼出し以外にある (想定外の IR)'
    assert len(CALL.findall(fn)) == 1, '呼出しの形が想定と違う'
    assert 'inttoptr (i64 1 to ptr)' not in fn, '適用済み (二重適用)'
    return CALL.sub(NEW, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    check_machine(a.pe)
    src = open(a.src, errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_815050 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(a.dst, 'w').write(out)
    print('[fix_r8b815050] function_815050: 6cefb0 の第 3 引数 (機械語 mov r8b,1 の即値 1) を inttoptr (i64 1 to ptr) に置換')


if __name__ == '__main__':
    main()
