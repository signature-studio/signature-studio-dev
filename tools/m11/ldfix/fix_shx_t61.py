#!/usr/bin/env python3
"""fix_shx_t61.py — #5855 (SHX-T61): callee function_4483f0 (Append) の入口に計装を入れる (実験・既定 OFF)。

呼出し回数 n と this+0x4c (IR 名 -28 の書込み index)・this+0x48 (IR 名 -32 の count) を、
@fx61_buf (i32 の配列) に書く。関数呼出しは使わない (genstubs が IR の declare を stub 化し、
名前衝突するため)。C 側の fx61_read (shimx_link/fx61_rec.c) が配列を読んで標準エラーへ出す。
呼出し回数が FX61_LIMIT (既定 100000) を超えたら unreachable で trap し、JS 側 (run_trace.mjs) が
_fx61_* を読む (hang しても記録を読めるようにするため)。
計装は callee の IR だけに入れる。親 function_448490 の IR・既定の IR は変えない。
想定と違う入力は assert で止める (fail-closed)。

使い方: python3 fix_shx_t61.py IN.ll OUT.ll
"""
import os
import re
import sys

LIMIT = int(os.environ.get('FX61_LIMIT', '100000'))   # 呼出し回数の上限。超えたら unreachable で trap し、JS 側で記録を読む
DEF = re.compile(r'^define i64 @function_4483f0\(ptr %arg1, i16 %arg2\) local_unnamed_addr \{\n', re.M)
ENTRY = 'dec_label_pc_4483f0:\n'
DATALAYOUT = re.compile(r'^target datalayout = [^\n]*\n', re.M)
# buf[0] = 呼出し回数 (i32 で十分)、buf[1] = 直近の this、buf[2] = 直近の +0x4c、buf[3] = 直近の +0x48
GLOBALS = '@fx61_buf = global [4 x i32] zeroinitializer, align 4\n'
PROBE = (ENTRY +
         '  %fx61n0 = load i32, ptr @fx61_buf, align 4\n'
         '  %fx61n1 = add i32 %fx61n0, 1\n'
         '  store i32 %fx61n1, ptr @fx61_buf, align 4\n'
         '  %fx61p76 = getelementptr i8, ptr %arg1, i64 76\n'
         '  %fx61v76 = load i32, ptr %fx61p76, align 4\n'
         '  %fx61p72 = getelementptr i8, ptr %arg1, i64 72\n'
         '  %fx61v72 = load i32, ptr %fx61p72, align 4\n'
         '  %fx61ptr = ptrtoint ptr %arg1 to i32\n'
         '  %fx61b1 = getelementptr i8, ptr @fx61_buf, i64 4\n'
         '  store i32 %fx61ptr, ptr %fx61b1, align 4\n'
         '  %fx61b2 = getelementptr i8, ptr @fx61_buf, i64 8\n'
         '  store i32 %fx61v76, ptr %fx61b2, align 4\n'
         '  %fx61b3 = getelementptr i8, ptr @fx61_buf, i64 12\n'
         '  store i32 %fx61v72, ptr %fx61b3, align 4\n'
         '  %fx61over = icmp sgt i32 %fx61n1, ' + str(LIMIT) + '\n'
         '  br i1 %fx61over, label %fx61trap, label %fx61cont\n'
         'fx61trap:\n'
         '  unreachable\n'
         'fx61cont:\n')


def patch(src):
    assert 'fx61' not in src, '適用済み (二重適用)'
    assert len(DEF.findall(src)) == 1, 'function_4483f0 の定義が想定と違う'
    dl = DATALAYOUT.search(src)
    assert dl, 'target datalayout が無い'
    src = src[:dl.end()] + GLOBALS + src[dl.end():]
    m = DEF.search(src)
    assert src[m.end():].startswith(ENTRY), 'entry label が想定と違う'
    out = src[:m.end()] + PROBE + src[m.end() + len(ENTRY):]
    assert out != src
    return out


def main():
    src = open(sys.argv[1], errors='replace').read()
    open(sys.argv[2], 'w').write(patch(src))
    print('[fix_shx_t61] function_4483f0: 入口に呼出し計数と this+0x4c / +0x48 の記録を追加 (実験)')


if __name__ == '__main__':
    main()
