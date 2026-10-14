#!/usr/bin/env python3
"""fix_ld108.py — #2316 (LD-108): 41a670 の head 解除ブロックの store 値を [arg1+0] の load に直す。

機械語 41a69c〜41a6a3: `mov rax,[rbp+0x50]; mov rax,[rax]; mov [head],rax` (rax = arg1、変位 0)。
IR (lift 段から) は store 値を `%2 = load [arg1+8]` (変位 8) で代用している (REPORT_735 §1.1 / REPORT_911 §1)。
本 pass は dec_label_pc_41a69c ブロックだけを対象に、`%2` を `load i64 [arg1+0]` の新しい SSA 値へ置換する。
関数内の他の使用 (呼び出し引数 %3 の元 %2 など) は変えない。想定と違う入力は assert で止める
(第 1 仮引数が `i64 %arg1` でない / store 行が想定と違う / 適用済み (二重適用) など。#2402)。

使い方: python3 fix_ld108.py IN.ll OUT.ll
"""
import os
import re
import sys

FN = re.compile(r'^define [^\n]*@function_41a670\(.*?\n}\n', re.M | re.S)
DEF = re.compile(r'^define [^\n]*@function_41a670\(([^)]*)\)', re.M)
ARG1 = re.compile(r'i64(?: [a-z_]+)* %arg1')
BLK = re.compile(r'^dec_label_pc_41a69c:[^\n]*\n(.*?)(?=^dec_label_pc_|\Z)', re.M | re.S)
# head 即値は LVA (= RVA + M11_LB_BASE)。LB=0 は 0xfa5080、LB=0x10000 は 0xfb5080 (#2779: 固定値だと LB=0x10000 で assert する)
LB = int(os.environ.get('M11_LB_BASE', '0'), 0)
HEAD_ST = 'store i64 %2, ptr inttoptr (i64 ' + str(16404608 + LB) + ' to ptr), align 8'
RAX_ST = 'store i64 %2, ptr %rax.0.reg2mem'


def patch(fn):
    d = DEF.match(fn)
    assert d, 'function_41a670 の define 行が読めない'
    first = d.group(1).split(',')[0].strip()
    assert ARG1.fullmatch(first), '第 1 仮引数が i64 %%arg1 でない: %r' % first
    m = BLK.search(fn)
    assert m, 'dec_label_pc_41a69c が無い'
    body = m.group(1)
    assert body.count(HEAD_ST) == 1 and body.count(RAX_ST) == 1, 'store 行が想定と違う'
    new = ('  %ldfx108p = inttoptr i64 %arg1 to ptr\n'
           '  %ldfx108 = load i64, ptr %ldfx108p, align 8\n')
    body2 = body.replace(HEAD_ST, HEAD_ST.replace('%2,', '%ldfx108,'))
    body2 = body2.replace(RAX_ST, RAX_ST.replace('%2,', '%ldfx108,'))
    return fn[:m.start(1)] + new + body2 + fn[m.end(1):]


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_41a670 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_ld108] function_41a670: 41a69c ブロックの head/rax store を [arg1+0] の load に置換')


if __name__ == '__main__':
    main()
