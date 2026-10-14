#!/usr/bin/env python3
"""ld108_irdiff.py — #2402 (LD-112): fix_ld108 の組込み前後の IR で、差があるのが function_41a670 の 1 関数だけであることを検算する。

IR を `define ... @name(...) ... }` の関数単位と、それ以外 (globals / declare / metadata) に分け、関数ごと・関数外の本文を比較する。
`diff` の行差分とは別の算法 (関数単位の文字列比較)。差のある関数が function_41a670 だけで、関数外が完全一致なら rc 0。

使い方: python3 ld108_irdiff.py PRE.ll POST.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@([\w$.]+)\(.*?\n}\n', re.M | re.S)


def split(path):
    s = open(path, errors='replace').read()
    fns, rest, pos = {}, [], 0
    for m in FN.finditer(s):
        rest.append(s[pos:m.start()])
        fns[m.group(1)] = m.group(0)
        pos = m.end()
    rest.append(s[pos:])
    return fns, ''.join(rest)


def main():
    fa, ra = split(sys.argv[1])
    fb, rb = split(sys.argv[2])
    diff = sorted(n for n in set(fa) | set(fb) if fa.get(n) != fb.get(n))
    print('LD108_IRDIFF functions pre=%d post=%d / 差のある関数 %d: %s / 関数外の本文 %s' % (
        len(fa), len(fb), len(diff), ' '.join(diff), '一致' if ra == rb else '不一致'))
    ok = diff == ['function_41a670'] and ra == rb
    print('LD108_IRDIFF_JUDGE', 'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
