#!/usr/bin/env python3
# SHX-T27 (#1630): 2 つの IR (.ll) の差分を要約する。
#   (1) 生の差分: hunk 数・変更行数・関数単位の内訳 (GNU diff)
#   (2) SSA 名 (%xxx) を %V に潰した差分: 番号の付け直しを除いた hunk 数・行の種別 (alloca / load・store / その他)
# 使い方: python3 t27_ir_diff.py <旧 IR> <新 IR>
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

old, new = sys.argv[1], sys.argv[2]
hdr = re.compile(r'^(\d+)(?:,(\d+))?([acd])(\d+)(?:,(\d+))?$')


def run_diff(a, b):
    return subprocess.run(['diff', a, b], capture_output=True, text=True).stdout.splitlines()


def defines(path):
    idx = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for n, line in enumerate(f, 1):
            if line.startswith('define '):
                m = re.search(r'@([\w.]+)\(', line)
                idx.append((n, m.group(1) if m else '?'))
    return idx


def func_of(idx, lineno):
    name = '(global)'
    for n, nm in idx:
        if n <= lineno:
            name = nm
        else:
            break
    return name


out = run_diff(old, new)
old_def, new_def = defines(old), defines(new)
hunks = 0
kind = {'<': Counter(), '>': Counter()}
funcs = Counter()
for line in out:
    m = hdr.match(line)
    if m:
        hunks += 1
        op = m.group(3)
        side_new = int(m.group(4)) if op != 'd' else None
        side_old = int(m.group(1)) if op != 'a' else None
        ln = side_new if side_new is not None else side_old
        func = func_of(new_def if side_new is not None else old_def, ln or 0)
        continue
    if line[:2] in ('< ', '> '):
        tag = line[0]
        cls = 'alloca' if re.search(r'=\s*alloca\b', line) else 'other'
        kind[tag][cls] += 1
        funcs[func] += 1

print('[生の差分]')
print(f'hunks: {hunks}')
for tag, label in (('<', 'old 側'), ('>', 'new 側')):
    c = kind[tag]
    print(f'{label}: 変更行 {sum(c.values())} (alloca {c["alloca"]} / その他 {c["other"]})')
print(f'関数単位: {len(funcs)} 関数に差分 (行数上位 10)')
for name, cnt in funcs.most_common(10):
    print(f'  {name} {cnt}')

tmp = tempfile.mkdtemp(prefix='t27_ir_', dir=os.environ.get('TMPDIR') or None)
norm = {}
for tag, path in (('old', old), ('new', new)):
    with open(path, 'rb') as f:
        data = re.sub(rb'%[A-Za-z0-9_.-]+', b'%V', f.read())
    norm[tag] = os.path.join(tmp, tag + '.ll')
    with open(norm[tag], 'wb') as f:
        f.write(data)

nout = run_diff(norm['old'], norm['new'])
nhunks = sum(1 for line in nout if hdr.match(line))
ncls = {'<': Counter(), '>': Counter()}
for line in nout:
    if line[:2] in ('< ', '> '):
        tag = line[0]
        if re.search(r'=\s*alloca\b', line):
            cls = 'alloca'
        elif re.search(r'=\s*load\b|^[<>] +store\b', line):
            cls = 'load/store'
        else:
            cls = 'その他'
        ncls[tag][cls] += 1
print('[SSA 名を %V に潰した差分]')
print(f'hunks: {nhunks}')
for tag, label in (('<', 'old 側'), ('>', 'new 側')):
    c = ncls[tag]
    print(f'{label}: 変更行 {sum(c.values())} (alloca {c["alloca"]} / load・store {c["load/store"]} / その他 {c["その他"]})')
