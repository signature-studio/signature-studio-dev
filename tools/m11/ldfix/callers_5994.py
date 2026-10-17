#!/usr/bin/env python3
# callers_5994.py — #5994 (LD-295): 関数の直接呼び出し元を IR から 2 段まで列挙する (静的・計装なし)。
# 使い方: python3 callers_5994.py IR.ll VA [VA ...]
#   IR = work/boot_final3.ll (m11_gen_ir2.sh の出力)。出力は関数ごとの呼び出し元の列 (function_<VA> 形式を VA に戻す)。
import re
import sys

ir, vas = sys.argv[1], sys.argv[2:]
cur = None
calls = {}
defined = set()
for ln in open(ir, errors='replace'):
    m = re.match(r'define [^@]*@(\S+?)\(', ln)
    if m:
        cur = m.group(1)
        defined.add(cur)
        continue
    if ln.startswith('}'):
        cur = None
        continue
    if cur is None:
        continue
    for c in re.findall(r'call [^@\n]*@(\w+)\(', ln):
        calls.setdefault(c, set()).add(cur)


def va(name):
    m = re.match(r'function_([0-9a-f]+)$', name)
    return m.group(1) if m else name


for v in vas:
    t = 'function_' + v
    print('%s defined=%s' % (v, t in defined))
    for c in sorted(calls.get(t, [])):
        second = sorted(calls.get(c, []))
        print('  caller %s -> callers %s' % (va(c), ' '.join(va(x) for x in second) or '(none)'))
