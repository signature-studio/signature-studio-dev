#!/usr/bin/env python3
"""entry_3972.py (#3972): 指定関数の入口ブロックの先頭に m11_wprobe(id, a1, a2, a3) を入れる (読み取りだけの計装).
  callchk_3972.py の出力に後段で掛ける。値は変えない (call の追加のみ)。
  usage: entry_3972.py <in.ll> <out.ll>
  対象: function_4133f0 (id=1, 2 引数: store i64 %arg2 -> *arg1)・function_414c70 (id=2, 3 引数)・
  function_43c4c0 (id=3, 3 引数)・function_414bb0 (id=4, 2 引数) (#5329: 414c70 より前の段を絞る)。"""
import re, sys

src, dst = sys.argv[1], sys.argv[2]
TARGETS = {'function_4133f0': (1, 2), 'function_414c70': (2, 3), 'function_43c4c0': (3, 3), 'function_414bb0': (4, 2)}
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
LABEL = re.compile(r'^[-a-zA-Z$._0-9"]+:')
out, pending = [], None
for line in open(src, errors='replace').read().split('\n'):
    m = DEF.match(line)
    if m:
        pending = TARGETS.get(m.group(1))
    out.append(line)
    if pending and LABEL.match(line):
        fid, nargs = pending
        args = ['i64 %%arg%d' % k for k in range(1, nargs + 1)] + ['i64 0'] * (3 - nargs)
        out.append('  call void @m11_wprobe(i32 %d, %s)' % (fid, ', '.join(args)))
        pending = None
out.append('declare void @m11_wprobe(i32, i64, i64, i64)')
open(dst, 'w').write('\n'.join(out))
