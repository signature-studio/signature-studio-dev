#!/usr/bin/env python3
"""copy_watch_3972.py (#3972): function_409c80 (copy; 16 バイト `store i128` で書くため store 計装に映らない) の入口に
m11_copy_in(dst, src, n, site) を入れる (#3972: unit 158 の `s = 0x10aa1428` への文字列の書込み元の特定)。
  usage: copy_watch_3972.py <in.ll> <out.ll>
  入口の計装は call の追加のみ (IR の値・分岐は不変)。C 側 (watch_copy_3972.c) が範囲判定し、重なるときだけ `[cp]` 行を出す。"""
import re, sys

src, dst = sys.argv[1], sys.argv[2]
DEF = re.compile(r'^define [^\n@]*@function_409c80\(i64 %arg1, i64 %arg2, i64 %arg3\) [^\n]*\{\s*$')
out, n_hit = [], 0
with open(src, errors='replace') as f:
    lines = f.readlines()
i = 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    if DEF.match(line):
        n_hit += 1
        # define 行の直後にラベル行 (dec_label_pc_409c80:) が続く。その直後に計装を入れる (entry block の先頭)
        j = i + 1
        while j < len(lines) and not lines[j].rstrip().endswith(':'):
            out.append(lines[j]); j += 1
        if j < len(lines):
            out.append(lines[j])
            out.append('  call void @m11_copy_in(i64 %arg2, i64 %arg1, i64 %arg3)\n')
            i = j + 1
            continue
    i += 1
if out and not out[-1].endswith('\n'):
    out[-1] += '\n'
out.append('declare void @m11_copy_in(i64, i64, i64)\n')
with open(dst, 'w') as f:
    f.writelines(out)
print(f'[copy_watch_3972] function_409c80 entry hooks: {n_hit}')
if n_hit != 1:
    sys.exit(1)
