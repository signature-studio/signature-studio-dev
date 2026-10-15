#!/usr/bin/env python3
"""fix_src412770.py — #3296: function_412770 の rep movsq 源 `ptr null` を機械語どおりの [arg1+0] の load に直す。

機械語 412790〜412796: `mov rsi,[rax]; mov rdi,rax; mov ecx,0x25; rep movsq` (rax = rcx = arg1、変位 0)。
源 rsi は [arg1+0] の**値** (1 段 deref) で、lift 段 (boot0.lift.ll) はこの load を脱落させ源を `ptr null` にしている。
NULL 源は wasm の address 0 を読む。address 0 の中身と unit 結果の LB 依存の関係は未確認 (REPORT_3296.md §4)。
本 pass は `call @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)` の 1 行だけを、`load i64 [arg1+0]` の結果を inttoptr した源に置換する。
想定と違う入力は assert で止める (第 1 仮引数が ptr %arg1 でない / 対象行が 1 件でない / 適用済み (二重適用) など。fail-closed)。

使い方: python3 fix_src412770.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_412770\(.*?\n}\n', re.M | re.S)
DEF = re.compile(r'^define [^\n]*@function_412770\(([^)]*)\)', re.M)
ARG1 = re.compile(r'ptr %arg1')
MEMCPY = '  call void @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)\n'
NEW = ('  %fx412770v = load i64, ptr %arg1, align 8\n'
       '  %fx412770 = inttoptr i64 %fx412770v to ptr\n'
       '  call void @__asm_rep_movsq_memcpy(ptr %4, ptr %fx412770, i64 37)\n')


def patch(fn):
    d = DEF.match(fn)
    assert d, 'function_412770 の define 行が読めない'
    first = d.group(1).split(',')[0].strip()
    assert ARG1.fullmatch(first), '第 1 仮引数が ptr %%arg1 でない: %r' % first
    assert fn.count(MEMCPY) == 1, 'rep movsq 源 ptr null の行が 1 件でない: %d' % fn.count(MEMCPY)
    assert 'fx412770' not in fn, '適用済み (二重適用)'
    return fn.replace(MEMCPY, NEW)


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_412770 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_src412770] function_412770: rep movsq 源 ptr null を [arg1+0] の load に置換')


if __name__ == '__main__':
    main()
