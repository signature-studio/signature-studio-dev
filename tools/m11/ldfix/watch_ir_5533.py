#!/usr/bin/env python3
# watch_ir_5533.py: boot_final.ll の function_1046a30 に値の観測フック m11_wv(id, value) を差し込む (#5533 受入 1・診断専用)。
# 観測点 (IR の SSA 名 · 機械語の対応):
#   id 1: %359 = X の段 1 の load ([Q+8]) ・ 機械語 10474bf〜10474c9 付近
#   id 2: %363 = X (= [rbp+0x4e8] の実行時値) ・ 機械語 10474d4〜10474d8
#   id 3: %491 = P (= X+0x16c = [rbp+0x4d8]) ・ 機械語 104796f〜1047942
#   id 4: zext(%505) = P の指す 4B の値 (= 10479c7 の入力 ・ 機械語 10479be〜10479c5)
# 使い方: python3 tools/m11/ldfix/watch_ir_5533.py <in.ll> <out.ll>
import re, sys

src, dst = sys.argv[1], sys.argv[2]
lines = open(src, errors='replace').read().split('\n')

start = end = None
for i, ln in enumerate(lines):
    if start is None and re.match(r'^define .*@function_1046a30\(', ln):
        start = i
    elif start is not None and ln.startswith('}'):
        end = i
        break
assert start is not None and end is not None, 'function_1046a30 が見つからない'

out_fn = []
hits = set()
for ln in lines[start:end + 1]:
    out_fn.append(ln)
    if re.match(r'^dec_label_pc_1046a30:', ln):
        out_fn.append('  call void @m11_wv(i64 0, i64 %arg3)'); hits.add(0)
    elif re.match(r'^  %359 = load i64, ptr %358, align 8$', ln):
        out_fn.append('  call void @m11_wv(i64 1, i64 %359)'); hits.add(1)
    elif re.match(r'^  %363 = load i64, ptr %362, align 8$', ln):
        out_fn.append('  call void @m11_wv(i64 2, i64 %363)'); hits.add(2)
    elif re.match(r'^  %491 = add i64 %363, 364$', ln):
        out_fn.append('  call void @m11_wv(i64 3, i64 %491)'); hits.add(3)
    elif re.match(r'^  %505 = load i32, ptr %492, align 4$', ln):
        # 次の行 (store i32 %505 → stack_var_16) の直前で読む値を記録する。%505 は後続で参照されるので定義直後に置く
        out_fn.append('  %w5533_4 = zext i32 %505 to i64')
        out_fn.append('  call void @m11_wv(i64 4, i64 %w5533_4)'); hits.add(4)
assert hits == {0, 1, 2, 3, 4}, 'フック点が揃わない: %s' % sorted(hits)

out = list(lines[:2]) + ['declare void @m11_wv(i64, i64)'] + lines[2:start] + out_fn + lines[end + 1:]
open(dst, 'w').write('\n'.join(out))
print('[watch_ir_5533] hooks: %s (function_1046a30 %d..%d)' % (sorted(hits), start + 1, end + 1))
