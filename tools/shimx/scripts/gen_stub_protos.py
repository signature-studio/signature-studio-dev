#!/usr/bin/env python3
"""shimx.h に宣言が無い公開関数の prototype を src/*.c の定義行から抽出し src/shimx_stubs.h に出力する。
  gen_stub_protos.py --nm work/nm_MT.txt
(shimx_stubs.h は shimx.h 末尾から #include される。自動生成物 — 手編集禁止)"""
import argparse, glob, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ap = argparse.ArgumentParser(); ap.add_argument('--nm', required=True); a = ap.parse_args()
defined = set()
for l in open(a.nm):
    p = l.split()
    if len(p) >= 2 and p[-2] in 'TWtw': defined.add(p[-1])
hdr = open(os.path.join(ROOT, 'src', 'shimx.h')).read()
hdr = hdr.split('#include "shimx_stubs.h"')[0]
declared = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', hdr))
und = sorted(n for n in defined if n not in declared and not n.startswith('shx_') and n != 'shim_unimplemented')
protos = {}
for f in sorted(glob.glob(os.path.join(ROOT, 'src', '*.c'))):
    if f.endswith('proctable.c'): continue
    for ln in open(f):
        m = re.match(r'^(?:SHIMX_WEAK\s+)?([A-Za-z_][\w\s\*]*?\b)(\w+)\(([^)]*)\)\s*\{', ln)
        if m and m.group(2) in und and m.group(2) not in protos:
            protos[m.group(2)] = '%s%s(%s);' % (m.group(1), m.group(2), m.group(3))
miss = [n for n in und if n not in protos]
out = ['/* 自動生成: scripts/gen_stub_protos.py — 手編集禁止 (shimx.h 未宣言の公開関数の prototype) */', '#ifndef SHIMX_STUBS_H', '#define SHIMX_STUBS_H', '#ifdef __cplusplus', 'extern "C" {', '#endif']
out += [protos[n] for n in und if n in protos]
out += ['#ifdef __cplusplus', '}', '#endif', '#endif']
open(os.path.join(ROOT, 'src', 'shimx_stubs.h'), 'w').write('\n'.join(out) + '\n')
print('stub protos: %d (抽出不能: %s)' % (len(protos), miss))
