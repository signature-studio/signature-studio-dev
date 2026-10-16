#!/usr/bin/env python3
"""#5715 (CI-238): function_439f90 の入口に計数 probe (volatile store) を入れた計測 IR を作る (計測専用).
  usage: m11_439f90_probe_insert.py <in.ll> <out.ll> <table.json>
  入口ラベル直後に `store volatile i32 1, ptr @m11_fe_439f90` を入れる。動作は変えない (global への store のみ)。
  probe 変数の実体は ldfix/m11_439f90_probe_rt.c。
"""
import json, re, sys

SRC, DST, TABLE = sys.argv[1], sys.argv[2], sys.argv[3]
DEF = re.compile(r'^define [^\n]*@function_439f90\(')
lines = open(SRC).read().split('\n')
out, done = [], 0
i = 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    if DEF.match(line):
        j = i + 1
        while j < len(lines) and not lines[j].endswith(':'):
            out.append(lines[j]); j += 1
        if j < len(lines):
            out.append(lines[j])
            out.append('  store volatile i32 1, ptr @m11_fe_439f90')
            done += 1
            i = j + 1
            continue
    i += 1
if done != 1:
    sys.exit('function_439f90 の定義が 1 件でない (%d 件): fail-closed' % done)
text = '\n'.join(out)
text = re.sub(r'(?m)^(target datalayout = .*)$',
              lambda mm: mm.group(1) + '\n@m11_fe_439f90 = external global i32',
              text, count=1)
open(DST, 'w').write(text)
json.dump({'fn': '439f90', 'inserted': done}, open(TABLE, 'w'), indent=1)
print('inserted', done)
