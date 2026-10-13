#!/usr/bin/env python3
"""[P-T2] 指定関数の呼出の i32 実引数を分類する (fix_i32_ptr_arg.py の検証用; #1485)。

使い方: classify_i32_callers.py IN.ll FUNC ARGINDEX
出力: 呼出 1 件ごとに 種別 (const / trunc / other:%V) を行で出し、最後に件数を出す。
  const : 0..2^31-1 の整数定数
  trunc : %V = trunc i64 %W to i32 (同一 define 内。距離制限なし)
  other : それ以外 (fix_i32_ptr_arg.py は失敗させる)"""
import re, sys

text, fn, k = open(sys.argv[1]).read().split('\n'), sys.argv[2], int(sys.argv[3])
cnt = {}
start = None
for i, l in enumerate(text):
    if l.startswith('define '):
        start = i
    m = re.search(r'call [^@]*@' + re.escape(fn) + r'\((.*)\)', l)
    if not m:
        continue
    parts = [p.strip() for p in m.group(1).split(',')]
    p = parts[k]
    if not p.startswith('i32 '):
        kind = 'other:not-i32'
    else:
        v = p[4:].strip()
        if re.fullmatch(r'-?\d+', v):
            kind = 'const'
        elif re.fullmatch(r'%[-\w.$]+', v) and any(
                re.match(r'^\s*' + re.escape(v) + r' = trunc i64 %\S+ to i32\s*$', text[q])
                for q in range(start, i)):
            kind = 'trunc'
        else:
            kind = 'other:' + v
    cnt[kind] = cnt.get(kind, 0) + 1
    print('line %d: %s' % (i + 1, kind))
print(cnt)
