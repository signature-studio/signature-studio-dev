#!/usr/bin/env python3
"""Extract MSVC RTTI type names (.?AV / .?AU) from a PE and classify by namespace/family. usage: rtti_classes.py <pe> <out_prefix>"""
import re, sys, collections
data = open(sys.argv[1], 'rb').read()
names = sorted(set(m.group(0).decode() for m in re.finditer(rb'\.\?A[UV][A-Za-z0-9_@$?]{2,300}@@', data)))
def demangle_simple(n):
    body = n[4:-2]
    parts = body.split('@')
    return '::'.join(reversed([p for p in parts if p]))
skip = re.compile(r'(\?\$|<lambda|std@@|Concurrency|nlohmann|details@|\$_)')
own, other = [], []
for n in names:
    (other if skip.search(n) else own).append(n)
fam = collections.Counter()
cls = []
for n in own:
    d = demangle_simple(n)
    cls.append(d)
open(sys.argv[2] + '_classes.txt', 'w').write('\n'.join(cls) + '\n')
open(sys.argv[2] + '_classes_all.txt', 'w').write('\n'.join(names) + '\n')
print(f"RTTI total={len(names)} own(non-template/std)={len(own)} templates/std/lambda={len(other)}")
