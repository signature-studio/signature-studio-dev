#!/usr/bin/env python3
"""reach_2408.py (#2408): boot_final3.ll の根関数から直接 call で到達する定義済み関数を数える (store_watch_2270.sh の WATCH_FNS 用)。
  usage: reach_2408.py [--src work/boot_final3.ll] [--roots function_8651a0,...] [--stores] > fns.txt
  出力: 1 行 1 関数 (BFS 順)。間接 call (m11_icall 経由) は辿らない。--stores で stderr に関数数と store 数も出す。"""
import os, re, sys
args = sys.argv[1:]
def opt(name, dflt):
    return args[args.index(name) + 1] if name in args else dflt
HERE = os.path.dirname(os.path.abspath(__file__)); M11 = os.path.join(HERE, '..')
src = opt('--src', os.path.join(M11, 'work', 'boot_final3.ll'))
roots = [r for r in opt('--roots', 'function_8651a0,function_40f9e0,function_410320,function_410360,function_409410').split(',') if r]
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
CALL = re.compile(r'\bcall\b[^@\n]*@([-a-zA-Z$._0-9"]+)\(')
bodies, calls, stores, fn = {}, {}, {}, None
for line in open(src):
    m = DEF.match(line)
    if m:
        fn = m.group(1); calls[fn] = set(); stores[fn] = 0; continue
    if fn is None:
        continue
    if line.startswith('}'):
        fn = None; continue
    for c in CALL.findall(line):
        calls[fn].add(c)
    if line.startswith(' ') and line.lstrip().startswith('store '):
        stores[fn] += 1
seen, order, q = set(), [], [r for r in roots if r in calls]
while q:
    f = q.pop(0)
    if f in seen:
        continue
    seen.add(f); order.append(f)
    for c in sorted(calls[f]):
        if c in calls and c not in seen:
            q.append(c)
for f in order:
    print(f)
if '--stores' in args:
    print('roots=%d reached=%d stores=%d' % (len(roots), len(order), sum(stores[f] for f in order)), file=sys.stderr)
