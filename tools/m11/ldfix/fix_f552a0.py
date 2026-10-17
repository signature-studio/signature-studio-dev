#!/usr/bin/env python3
"""fix_f552a0.py — #5999 (CI-249): function_f552a0 の呼出し第 1 引数を機械語どおりに戻す。

機械語 (block00031_PE.bin・capstone 実測。#5995 のコメント 6228635866 の表):
  f552a7 で `mov rbx, rcx` (rbx = 入口の %arg1)。f552aa は `cmp qword ptr [rbx], 0`。
  f552b6 / f552ce / f552e8 / f55318 / f5531d / f5532b / f5534b / f5536d は全て `mov rcx, qword ptr [rbx]` で
  rcx を入口の [rbx] (= [%arg1] の 8 バイト load) から読み直してから `call 0x12df530` する。
  f5539c の `call 0x12df760` の直前も `mov rcx, qword ptr [rbx]`。
  よって呼出し第 1 引数は %arg1 そのものではなく、%arg1 が指す先から load した値 (構造体ポインタ)。

現行 IR (ldfix 後) の誤り:
  (A) f5531d の呼出し第 1 引数が %21 (境界値 [p+0x10]-1 の sext) になっている。
  (B) ループ内の呼出し第 1 引数が %rcx.0.reload (loop-carry) で、2 反復目以降は %21 等の値が入る。
  (C) 脱出後の 12df760 の第 1 引数も %rcx.1.reload (loop-carry)。

本 pass は、loop-carry の rcx.0 / rcx.1 のスロットを全て外し、6 箇所の呼出しの直前に
「%arg1 を ptr に変換して i64 を load する」2 命令を挿入して、その結果を第 1 引数にする。
%arg1 は i64 (整数) なので load の前に inttoptr が要る。load は各 call の直前に置くため、
ループ内では反復ごとに読み直す。他の行は変えない。想定と違う入力は assert で止める (fail-closed)。

使い方: python3 fix_f552a0.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_f552a0\(.*?\n}\n', re.M | re.S)
HEAD = 'define i64 @function_f552a0(i64 %arg1) '

ALLOCA_RE = re.compile(r'^  %rcx\.[01]\.reg2mem = alloca i64\n', re.M)
LOAD_RE = re.compile(r'^  %rcx\.[01]\.reload = load i64, ptr %rcx\.[01]\.reg2mem\n', re.M)
STORE_RE = re.compile(r'^  store i64 [^\n]*, ptr %rcx\.[01]\.reg2mem\n', re.M)

# (元の call 行, 第 1 引数の元の値, 呼出し名, 挿入する load の接尾辞)
CALL_LOOP_NS = ('5', '10', '29', '35')
CALL_LOOP = '  %{n} = call i64 @function_12df530(i64 %rcx.0.reload, i64 %rsi.0.reload)\n'
CALL_F5531D_OLD = '  %24 = call i64 @function_12df530(i64 %21, i64 %rsi.0.reload)\n'
CALL_EXIT_OLD = '  %45 = call i64 @function_12df760(i64 %rcx.1.reload)\n'

LOAD_ARG = ('  %fx5999p{t} = inttoptr i64 %arg1 to ptr\n'
            '  %fx5999o{t} = load i64, ptr %fx5999p{t}, align 8\n')


def load_arg(t):
    return LOAD_ARG.format(t=t)


def patch(fn):
    head = fn.split('\n', 1)[0] + ' '
    assert fn.startswith(HEAD), 'function_f552a0 の仮引数が想定と違う: %r' % fn.split('\n', 1)[0]
    assert 'fx5999' not in fn, '適用済み (二重適用)'
    assert len(ALLOCA_RE.findall(fn)) == 2, 'rcx.0/rcx.1 の alloca が 2 件でない'
    assert len(LOAD_RE.findall(fn)) == 2, 'rcx.0/rcx.1 の reload が 2 件でない'
    for n in CALL_LOOP_NS:
        assert fn.count(CALL_LOOP.format(n=n)) == 1, 'ループ内の呼出し %%%s が想定と違う' % n
    assert fn.count(CALL_F5531D_OLD) == 1, 'f5531d の呼出しが想定と違う'
    assert fn.count(CALL_EXIT_OLD) == 1, '脱出後の呼出しが想定と違う'
    out = fn
    for n in CALL_LOOP_NS:
        old = CALL_LOOP.format(n=n)
        new = load_arg(n) + '  %{n} = call i64 @function_12df530(i64 %fx5999o{n}, i64 %rsi.0.reload)\n'.format(n=n)
        out = out.replace(old, new)
    out = out.replace(CALL_F5531D_OLD,
                      load_arg('24') + '  %24 = call i64 @function_12df530(i64 %fx5999o24, i64 %rsi.0.reload)\n')
    out = out.replace(CALL_EXIT_OLD,
                      load_arg('45') + '  %45 = call i64 @function_12df760(i64 %fx5999o45)\n')
    out = ALLOCA_RE.sub('', out)
    out = LOAD_RE.sub('', out)
    out = STORE_RE.sub('', out)
    assert not re.search(r'rcx\.[01]\.', out), 'rcx.0/rcx.1 の参照が残っている'
    assert out.count('= load i64, ptr %fx5999p') == 6, '挿入した load が 6 件でない'
    return out


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_f552a0 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_f552a0] function_f552a0: 呼出し第 1 引数を機械語 [rbx] (= *%arg1) に戻し、rcx.0/rcx.1 の loop-carry を外す')


if __name__ == '__main__':
    main()
