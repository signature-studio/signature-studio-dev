#!/usr/bin/env python3
"""fix_shx_t61b.py — #5855 (SHX-T61 次段): 親 function_448490 の外側 loop の入口に計装を入れる (実験・既定 OFF)。

外側 loop は dec_label_pc_4484f4 (添字 -32.0 を reload する) で、dec_label_pc_448731 の
  %106 = icmp slt i64 %9, %105   (%9 = [arg2-4] 由来の上限、%105 = -32.2 の sext)
で続くかを決める。この入口の通過回数 n と、上限 %9 (下位 32 bit)・添字 -32.0 を
@fx61b_buf (i32 の配列) に書く。n が FX61B_LIMIT (既定 100000) を超えたら unreachable で trap し、
JS 側 (run_trace.mjs) が _fx61b_* を読む (fix_shx_t61.py と同じ方式)。
計装は親の IR の loop 入口だけに入れる。記録のための load・store だけで分岐の結果は変えない。
想定と違う入力は assert で止める (fail-closed)。

使い方: python3 fix_shx_t61b.py IN.ll OUT.ll
"""
import os
import re
import sys

LIMIT = int(os.environ.get('FX61B_LIMIT', '100000'))
DEF = re.compile(r'^define i64 @function_448490\(i64 %arg1, i64 %arg2, i32 %arg3, i16 %arg4\) local_unnamed_addr \{\n', re.M)
DATALAYOUT = re.compile(r'^target datalayout = [^\n]*\n', re.M)
GLOBALS = '@fx61b_buf = global [4 x i32] zeroinitializer, align 4\n'
LOOP = 'dec_label_pc_4484f4:                              ; preds = %dec_label_pc_4484f4.preheader, %dec_label_pc_448731\n'
# buf[0] = 入口の通過回数 n, buf[1] = 上限 %9 (下位 32 bit), buf[2] = 添字 -32.0 の直近値
PROBE = (LOOP +
         '  %fx61bn0 = load i32, ptr @fx61b_buf, align 4\n'
         '  %fx61bn1 = add i32 %fx61bn0, 1\n'
         '  store i32 %fx61bn1, ptr @fx61b_buf, align 4\n'
         '  %fx61bt9 = trunc i64 %9 to i32\n'
         '  %fx61bb1 = getelementptr i8, ptr @fx61b_buf, i64 4\n'
         '  store i32 %fx61bt9, ptr %fx61bb1, align 4\n'
         '  %fx61bi0 = load i32, ptr %stack_var_-32.0.reg2mem, align 4\n'
         '  %fx61bb2 = getelementptr i8, ptr @fx61b_buf, i64 8\n'
         '  store i32 %fx61bi0, ptr %fx61bb2, align 4\n'
         '  %fx61bi2 = load i32, ptr %stack_var_-32.2.reg2mem, align 4\n'
         '  %fx61bb3 = getelementptr i8, ptr @fx61b_buf, i64 12\n'
         '  store i32 %fx61bi2, ptr %fx61bb3, align 4\n'
         '  %fx61bover = icmp sgt i32 %fx61bn1, ' + str(LIMIT) + '\n'
         '  br i1 %fx61bover, label %fx61btrap, label %fx61bcont\n'
         'fx61btrap:\n'
         '  unreachable\n'
         'fx61bcont:\n')


def patch(src):
    assert 'fx61b' not in src, '適用済み (二重適用)'
    assert len(DEF.findall(src)) == 1, 'function_448490 の定義が想定と違う'
    assert src.count(LOOP) == 1, 'loop 入口のラベル行が 1 件でない: %d' % src.count(LOOP)
    dl = DATALAYOUT.search(src)
    assert dl, 'target datalayout が無い'
    src = src[:dl.end()] + GLOBALS + src[dl.end():]
    out = src.replace(LOOP, PROBE)
    assert out != src
    return out


def main():
    src = open(sys.argv[1], errors='replace').read()
    open(sys.argv[2], 'w').write(patch(src))
    print('[fix_shx_t61b] function_448490: 外側 loop 入口に通過回数と上限・添字の記録を追加 (実験)')


if __name__ == '__main__':
    main()
