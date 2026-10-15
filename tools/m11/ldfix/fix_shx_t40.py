#!/usr/bin/env python3
"""fix_shx_t40.py — #3234 (SHX-T40, D23): function_448490 の親フレーム object (%stack_var_-104) を callee の view に合わせる (実験・既定 OFF)。

親 (機械語 prologue): rbp = entry_rsp - 104。callee function_4483f0 (Append) は this = rbp を受け、[this+0x70]・[this+0x4c]・[this+0x48] を読み書きする。
  1. 拡幅: object の alloca を [15 x i64] (120 B) にする (callee は +0x78 まで触る)。生成段階の入力は alloca i64 (8 B) か [6 x i64] (48 B)。
  2. 機械語 0x4484b3 `mov [rbp+0x70], rcx`: entry の %arg1 を object の +0x70 に書く。
  3. 機械語 0x4484e4 `mov dword [rbp+0x4c], 1`: object の +0x4c (IR 名 -28) に i32 1 を書く (IR に無かった初期 store)。
count (+0x48 / IR 名 -32) の call 前後の同期は本 pass では行わない。
実測: 本 pass を入れると unit 18 で hang (rc 124)。+0x4c の store を外すと OOB。tools/m11/REPORT_SHX-T40.md §3。
想定と違う入力は assert で止める (fail-closed)。

使い方: python3 fix_shx_t40.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_448490\(.*?\n}\n', re.M | re.S)
DEF_HEAD = 'define i64 @function_448490(i64 %arg1, '
ALLOCA_RE = re.compile(r'^  %stack_var_-104 = alloca (?:i64|\[6 x i64\]), align 8\n', re.M)
ALLOCA_NEW = '  %stack_var_-104 = alloca [15 x i64], align 8\n'
ENTRY_ANCHOR = '  store i64 0, ptr %stack_var_-56, align 8\n'
ENTRY_NEW = (ENTRY_ANCHOR +
             '  %fx40home = getelementptr i8, ptr %stack_var_-104, i64 112\n'
             '  store i64 %arg1, ptr %fx40home, align 8\n'
             '  %fx40len = getelementptr i8, ptr %stack_var_-104, i64 76\n'
             '  store i32 1, ptr %fx40len, align 4\n')


ENTRY_NEW_70ONLY = (ENTRY_ANCHOR +
                    '  %fx40home = getelementptr i8, ptr %stack_var_-104, i64 112\n'
                    '  store i64 %arg1, ptr %fx40home, align 8\n')


def patch(fn, only70=False):
    assert fn.startswith(DEF_HEAD), 'function_448490 の仮引数が想定と違う'
    assert 'fx40' not in fn, '適用済み (二重適用)'
    n = len(ALLOCA_RE.findall(fn))
    assert n == 1, 'object の alloca 行が 1 件でない: %d' % n
    assert fn.count(ENTRY_ANCHOR) == 1, 'entry の anchor 行が 1 件でない: %d' % fn.count(ENTRY_ANCHOR)
    fn = ALLOCA_RE.sub(ALLOCA_NEW, fn)
    fn = fn.replace(ENTRY_ANCHOR, ENTRY_NEW_70ONLY if only70 else ENTRY_NEW)
    return fn


def main():
    only70 = len(sys.argv) > 3 and sys.argv[3] == '--only-70'
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_448490 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f, only70) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_shx_t40] function_448490: object 拡幅 (120 B)・+0x70 に arg1' + ('' if only70 else '・+0x4c に初期 1') + ' (実験)')


if __name__ == '__main__':
    main()
