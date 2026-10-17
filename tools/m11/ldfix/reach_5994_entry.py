#!/usr/bin/env python3
# reach_5994_entry.py — #5994 (LD-295): 47a250 の wrapper 入口に label を足した IR のコピーを作り、
#   計装対象 (10 対象 + 47a250 + 47a250 の function_ 呼び出し元) の VA 列を出す。
# 使い方: python3 reach_5994_entry.py IR.ll OUT_IR.ll > targets.txt
#   その後: IR=OUT_IR.ll bash ldfix/reach_509.sh "$(cat targets.txt)" OUT.json
# 理由: reach_509.sh は定義直後の label 行に挿入するため、本体が call だけの wrapper (function_47a250) は入口を計装できない。
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
TARGETS = 'db6480 dc27c0 ddd4d0 41b8d0 41b970 449550 44fb40 784ed0 c40420 f552a0'.split()
s = open(src, errors='replace').read()
old = 'define weak i64 @function_47a250(i64 %p0, i64 %p1, i64 %p2, i64 %p3) {\n'
assert s.count(old) == 1, '47a250 wrapper の定義が 1 件でない'
s = s.replace(old, old + 'entry:\n')
open(dst, 'w').write(s)
cur = None
callers = []
for ln in s.split('\n'):
    m = re.match(r'define [^@]*@(\S+?)\(', ln)
    if m:
        cur = m.group(1)
        continue
    if ln.startswith('}'):
        cur = None
        continue
    if cur and re.search(r'call [^@\n]*@function_47a250\(', ln) and cur not in callers:
        callers.append(cur)
vas = ['47a250'] + TARGETS + [c[len('function_'):] for c in callers
                              if re.fullmatch(r'function_[0-9a-f]+', c) and c != 'function_47a250']
vas = list(dict.fromkeys(vas))
print(','.join(vas))
