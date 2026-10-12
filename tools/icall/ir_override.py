#!/usr/bin/env python3
"""ir_override.py IN.ll OUT.ll VA[,VA...] — 指定 VA の lifted 関数 `define ... @function_<va>(...) {...}` を除去し declare に置換する。
実体は C 側 (rt/icall_ovr.c) が同名 `function_<va>` で定義する (BLK memory-ABI)。
用途: CRT 未初期化 (DllMain 未実行) で暗号化 fn ptr 経由の間接 call に落ちる数学エラー報告経路を、UCRT の観測可能な意味だけに置換する。
出力: 置換した関数と、元の定義の引数個数を stdout に JSON 1 行。指定 VA が IR に無ければ exit 1 (取りこぼし防止)。"""
import json, re, sys

src, dst, vas = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
lines = open(src, errors='replace').read().split('\n')
out, done, i = [], {}, 0
want = {v.lower() for v in vas}
while i < len(lines):
    m = re.match(r'^define (\S+) @function_([0-9a-f]+)\((.*?)\)', lines[i])
    if m and m.group(2) in want:
        nargs = len([a for a in m.group(3).split(',') if a.strip()])
        done[m.group(2)] = nargs
        out.append('declare %s @function_%s(%s)' % (m.group(1), m.group(2), ', '.join(['i64'] * nargs)))
        while not lines[i].startswith('}'):
            i += 1
        i += 1
        continue
    out.append(lines[i])
    i += 1
open(dst, 'w').write('\n'.join(out))
missing = sorted(want - set(done))
print(json.dumps({'overridden': done, 'missing': missing}))
sys.exit(1 if missing else 0)
