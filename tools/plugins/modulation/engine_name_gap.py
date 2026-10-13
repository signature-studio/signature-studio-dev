#!/usr/bin/env python3
"""engine lift の「define 無し range」を、RetDec の関数名で再照合する。
engine_defs.py は `function_<開始VA>` だけを数えるため、RetDec が export 名・既知名
(例: dispatch / entry_point) で define した range を欠落と誤判定する。
本スクリプトは e.drc.c の `// Address range: <a> - <e>` 注釈から、各 range の
RetDec 関数名 (定義行の識別子) を取り、final.ll の define 名と突き合わせる。
  usage: engine_name_gap.py <outdir>
  stdout: 1 行 → named_define, va_only_missing, va_only_missing_bytes, unresolved(list)
"""
import os, re, sys
d = sys.argv[1]
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(os.path.join(d, 'ranges.txt')).read().strip().split(',')]
ll = open(os.path.join(d, 'e.final.ll')).read()
dnames = set(re.findall(r'^define [^@]*@([A-Za-z_][A-Za-z0-9_.]*)\b', ll, re.M))
src = open(os.path.join(d, 'e.drc.c')).read()
name_at = {}
lines = src.split('\n')
n_ann = 0
for i, ln in enumerate(lines):
    m = re.match(r'// Address range: 0x([0-9a-f]+) - 0x[0-9a-f]+', ln)
    if not m:
        continue
    n_ann += 1
    h = re.match(r'[^\n(]*?\b([A-Za-z_]\w*)\s*\(', lines[i + 1] if i + 1 < len(lines) else '')
    if h:
        name_at[int(m.group(1), 16)] = h.group(1)
if len(name_at) != n_ann:
    sys.exit('annotation/name mismatch: annotations=%d names=%d' % (n_ann, len(name_at)))
va_defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
miss_va = [(a, e) for a, e in rg if a not in va_defs]
named = [(a, e) for a, e in miss_va if name_at.get(a) in dnames]
rest = [(a, e) for a, e in miss_va if (a, e) not in named]
print('%d,%d,%d,%s' % (len(named), len(rest), sum(e - a + 1 for a, e in rest),
      ';'.join('%x:%s' % (a, name_at.get(a, '?')) for a, _ in named + rest)))
