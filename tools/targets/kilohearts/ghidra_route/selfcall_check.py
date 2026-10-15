#!/usr/bin/env python3
"""ghidra_to_c.py の出力 (<name>.c) で、関数本体が自分自身の FUN_<va> を呼ぶ箇所を数える (thunk 正規化の誤りの検出)。
  python3 ghidra_route/selfcall_check.py <name>.c
出力: 自己呼出しを含む関数数 (0 が正常)。関数の境界は列 0 の定義行 (`型 FUN_<va>(...)`・末尾が `;` でない) で決める。
"""
import re
import sys

DEF = re.compile(r'^[A-Za-z_][\w \*]*?\s+FUN_([0-9a-f]+)\(')
cur = None
hits = {}
for line in open(sys.argv[1]).read().split('\n'):
    if line.startswith('EMSCRIPTEN_KEEPALIVE'):
        continue
    m = DEF.match(line)
    if m and not line.rstrip().endswith(';'):
        cur = m.group(1)
        continue
    if cur and line[:1] in (' ', '\t') and re.search(r'\bFUN_%s\(' % cur, line):
        hits.setdefault(cur, 0)
        hits[cur] += 1
print('self-call functions: %d (lines %d)' % (len(hits), sum(hits.values())))
for va, n in sorted(hits.items())[:20]:
    print('  FUN_%s : %d' % (va, n))
