#!/usr/bin/env python3
"""[P-D1] 同一 `declare` 行の重複除去 (plugins 追加 pass)。
観測: ir5_patch 後に `declare i64 @function_4362f0()` が 2 箇所に現れ clang が
"invalid redefinition of function" を出す (T0 バッチ 42 本中 5 本)。完全一致重複のみ除去。
使い方: fix_dup_decls.py IN.ll OUT.ll"""
import sys
seen = set()
out = []
n = 0
for l in open(sys.argv[1]).read().split('\n'):
    if l.startswith('declare '):
        if l in seen:
            n += 1
            continue
        seen.add(l)
    out.append(l)
open(sys.argv[2], 'w').write('\n'.join(out))
print('[P-D1] 重複 declare 除去 %d 件' % n, file=sys.stderr)
