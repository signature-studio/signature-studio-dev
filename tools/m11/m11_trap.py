#!/usr/bin/env python3
"""m11_trap.py: m11_boot.cjs を実行し, trap スタックの wasm-function[N] を export 名で注釈する.
 使い方: python3 m11_trap.py [--trace]   (--trace: M11 icall/unit トレースを有効化)"""
import subprocess, re, sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work')
wasm = os.path.join(W, 'm11_boot.cjs.wasm')
ex = subprocess.run(['wasm-objdump', '-x', '-j', 'Export', wasm], capture_output=True, text=True).stdout
names = {int(m.group(1)): m.group(2) for m in re.finditer(r'- func\[(\d+)\] <([^>]*)>', ex)}
imp = subprocess.run(['wasm-objdump', '-x', '-j', 'Import', wasm], capture_output=True, text=True).stdout
for m in re.finditer(r'- func\[(\d+)\] sig=\d+ <([^>]*)>', imp):
    names.setdefault(int(m.group(1)), 'import:' + m.group(2))
trace = '1' if '--trace' in sys.argv else '0'
r = subprocess.run(['node', os.path.join(HERE, 'm11_run.mjs')], capture_output=True, text=True, env=dict(os.environ, M11_TRACE=trace))
out = r.stdout + r.stderr
def ann(m):
    i = int(m.group(1))
    return 'wasm-function[%d]<%s>' % (i, names.get(i, '?'))
out = re.sub(r'wasm-function\[(\d+)\]', ann, out)
print(out)
