#!/usr/bin/env python3
"""fix_ld115.py — #2447 (LD-115): function_666a60 のループの 2 箇所を機械語に合わせて直す。

  count: ループ回数の初期値 (entry ブロック)。機械語 666ada〜666ae6: `mov edx,[r14]; sub edx,1; ...; sub edx,ecx; add edx,1`
         = edx は [N] (N.count = arg2 を 666a9e で書いた直後の値) に等しい。現行 ldfix 出力は
         `store i64 0, ptr %rdx.0.reg2mem` で、ループが 2^32 回回る (wasm では store がメモリ外へ出て trap する)。
         本 pass は store の値を `zext(load i32 [%15])` (%15 = N、機械語の [r14] と同じ読み) に置換する。
  store: ループ本体のスロット +16 (機械語 666b0c〜666b13: `mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10],r8`)。
         slot[i] の +16 へ書くのは N (= *arg1) である。現行 ldfix 出力は `store i64 %29, ptr %36` で、%29 は
         slot[i] のアドレス (N+64+32*i) を書く (REPORT_509 §1・REPORT_735 §1.2)。
         本 pass は値を `load i64 [%arg1]` (ループ内で毎回読む。機械語の 2 命令と同じ) へ置換する。
どちらも他の行は変えない。想定と違う入力は assert で止める。

使い方: python3 fix_ld115.py IN.ll OUT.ll [--only count|store]
  --only を省くと両方を適用する (本番候補)。--only count は store だけ未修復の中間版 (動的確認の negctl 用)。
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_666a60\(.*?\n}\n', re.M | re.S)
HEAD = 'define i64 @function_666a60(i64 %arg1, '
ENTRY = re.compile(r'^dec_label_pc_666a60:[^\n]*\n(.*?)(?=^dec_label_pc_|\Z)', re.M | re.S)
LOOP = re.compile(r'^dec_label_pc_666aeb:[^\n]*\n(.*?)(?=^dec_label_pc_|\Z)', re.M | re.S)
NPTR = re.compile(r'^  %15 = inttoptr i64 %\w+ to ptr\n', re.M)
N_STORE = '  store i32 %10, ptr %15, align 4\n'
CNT_ST = '  store i64 0, ptr %rdx.0.reg2mem\n'
CNT_NEW = ('  %ldfx115c = load i32, ptr %15, align 4\n'
           '  %ldfx115z = zext i32 %ldfx115c to i64\n'
           '  store i64 %ldfx115z, ptr %rdx.0.reg2mem\n')
ST = '  store i64 %29, ptr %36, align 8\n'
ST_NEW = ('  %ldfx115p = inttoptr i64 %arg1 to ptr\n'
          '  %ldfx115 = load i64, ptr %ldfx115p, align 8\n'
          '  store i64 %ldfx115, ptr %36, align 8\n')


def patch_count(fn):
    m = ENTRY.search(fn)
    assert m, 'dec_label_pc_666a60 が無い'
    body = m.group(1)
    assert NPTR.search(body) and N_STORE in body, 'N のポインタ %15 (arg2 の書込み先) が entry に無い'
    assert body.count(CNT_ST) == 1, 'rdx の初期化行が想定と違う (%d 件)' % body.count(CNT_ST)
    body2 = body.replace(CNT_ST, CNT_NEW)
    return fn[:m.start(1)] + body2 + fn[m.end(1):]


def patch_store(fn):
    m = LOOP.search(fn)
    assert m, 'dec_label_pc_666aeb が無い'
    body = m.group(1)
    assert '  %29 = add i64 %26, %28\n' in body and '  %36 = inttoptr i64 %35 to ptr\n' in body, 'ループ本体の定義行が想定と違う'
    assert body.count(ST) == 1, 'loop store 行が想定と違う (%d 件)' % body.count(ST)
    body2 = body.replace(ST, ST_NEW)
    return fn[:m.start(1)] + body2 + fn[m.end(1):]


def patch(fn, only=None):
    assert fn.startswith(HEAD), 'function_666a60 の仮引数が想定と違う'
    assert 'ldfx115' not in fn, '既に修復済み'
    if only in (None, 'count'):
        fn = patch_count(fn)
    if only in (None, 'store'):
        fn = patch_store(fn)
    return fn


def main():
    args = sys.argv[1:]
    only = None
    if '--only' in args:
        i = args.index('--only')
        only = args[i + 1]
        assert only in ('count', 'store'), '--only は count か store'
        del args[i:i + 2]
    src = open(args[0], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_666a60 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f, only) + src[fns[0].end():]
    assert out != src
    open(args[1], 'w').write(out)
    print('[fix_ld115] function_666a60: %s' % ('ループ回数の初期値 + ループ内 store' if only is None else only + ' のみ'))


if __name__ == '__main__':
    main()
