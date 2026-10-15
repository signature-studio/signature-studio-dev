#!/usr/bin/env python3
"""fix_ld116.py — #2513 (LD-116): function_666a60 の entry に回数 0 の早期脱出を入れる。

  機械語 666ada〜666ae8: `mov edx,[r14]; sub edx,1; mov eax,ecx; cmp eax,edx; jg 0x666b29` (ecx = 0)
          = edx = [N] - 1 (i32) が負なら (回数 ≤ 0) exit へ飛ぶ。exit (666b29) の戻り値は eax = 0。
          現行 IR の entry は無条件 `br label %dec_label_pc_666aeb` で、この分岐が無い。回数 0 では
          ループが 2^32 回回り wasm で trap する (REPORT_2447 §2.4)。
  本 pass は entry の末尾の無条件 br を、[N] (機械語 [r14] と同じ読み) から作った条件分岐に置換する。
  exit ブロックの ret は phi で受ける (早期脱出は 0、ループ経路は従来どおり %40)。
  fix_ld115.py の 2 箇所 (回数初期値・ループ内 store) は変えない。想定と違う入力は assert で止める。

使い方: python3 fix_ld116.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_666a60\(.*?\n}\n', re.M | re.S)
HEAD = 'define i64 @function_666a60(i64 %arg1, '
ENTRY = re.compile(r'^dec_label_pc_666a60:[^\n]*\n(.*?)(?=^dec_label_pc_|\Z)', re.M | re.S)
BR = '  br label %dec_label_pc_666aeb\n'
BR_NEW = ('  %ldfx116c = load i32, ptr %15, align 4\n'
          '  %ldfx116d = sub i32 %ldfx116c, 1\n'
          '  %ldfx116e = icmp slt i32 %ldfx116d, 0\n'
          '  br i1 %ldfx116e, label %dec_label_pc_666b29, label %dec_label_pc_666aeb\n')
EXIT_OLD = 'dec_label_pc_666b29:                              ; preds = %dec_label_pc_666aeb\n  ret i64 %40\n'
EXIT_NEW = ('dec_label_pc_666b29:                              ; preds = %dec_label_pc_666aeb, %dec_label_pc_666a60\n'
            '  %ldfx116r = phi i64 [ %40, %dec_label_pc_666aeb ], [ 0, %dec_label_pc_666a60 ]\n'
            '  ret i64 %ldfx116r\n')


def patch_entry(fn):
    m = ENTRY.search(fn)
    assert m, 'dec_label_pc_666a60 が無い'
    body = m.group(1)
    assert '  %15 = inttoptr i64 %ldfxu18 to ptr\n' in body, 'N のポインタ %15 が entry に無い'
    assert body.count(BR) == 1, 'entry の br 行が想定と違う (%d 件)' % body.count(BR)
    body2 = body.replace(BR, BR_NEW)
    return fn[:m.start(1)] + body2 + fn[m.end(1):]


def patch_exit(fn):
    assert fn.count(EXIT_OLD) == 1, '666b29 の ret ブロックが想定と違う (%d 件)' % fn.count(EXIT_OLD)
    return fn.replace(EXIT_OLD, EXIT_NEW)


def patch(fn):
    assert fn.startswith(HEAD), 'function_666a60 の仮引数が想定と違う'
    assert 'ldfx116' not in fn, '既に修復済み'
    fn = patch_entry(fn)
    fn = patch_exit(fn)
    return fn


def main():
    args = sys.argv[1:]
    assert len(args) == 2, '使い方: fix_ld116.py IN.ll OUT.ll'
    src = open(args[0], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_666a60 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(args[1], 'w').write(out)
    print('[fix_ld116] function_666a60: 回数 0 の早期脱出 (entry の条件分岐 + exit の phi)')


if __name__ == '__main__':
    main()
