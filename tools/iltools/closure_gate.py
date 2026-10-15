#!/usr/bin/env python3
"""closure_gate.py: x64c の lift_meta.json を export 閉包 gate で判定する (T-SH-12 #154)。
PASS 条件: 閉包 functions 824 / unsup 0 / unlifted callees 0 / trap stub 45 (閉包外の x87 関数)。違えば exit 1。
usage: closure_gate.py lift_meta.json"""
import json, sys

EXP_FUNCS, EXP_TRAPS = 824, 45
m = json.load(open(sys.argv[1]))
n = sum(m['unsup'].values())
nf, nt = len(m['functions']), len(m['traps'])
print('[iltools] closure functions %d / unsupported sites %d %s / unlifted callees %d / imports %d / trap stubs %d' % (
    nf, n, m['unsup'] or '', len(m['unlifted_callees']), len(m['imports_used']), nt))
ok = nf == EXP_FUNCS and n == 0 and not m['unlifted_callees'] and nt == EXP_TRAPS and not set(m['traps']) & set(m['functions'])
print('[iltools] %s' % ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
