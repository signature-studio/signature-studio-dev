#!/usr/bin/env python3
"""k80_deref_fix.py — レジスタ経由の deref が IR で落ちた kernel の修復 (#983 / REPORT §14.6)。

  python3 k80_deref_fix.py IN.ll OUT.ll [--report r.json]

対象 (機械語を読んで確認済み):
  0x5dee90 / 0x5df040: 先頭の `movups xmm7,[r10]` (r10 = r9 = 第 4 引数 arg4) の読み元が、
      RetDec で `%r9` の alloca (初期化されない) になっていた。機械語どおり arg4 を指す。
  0x5e02b0: `mov rdx,[rdx]` (引数 record の第 1 qword を base にする) が落ち、
      2 本目の出力 base に引数ポインタ自体 (arg2) を使っていた。機械語どおり [arg2] を読む。

いずれも関数単位の文字列置換で、置換箇所の一致回数を assert する (不一致なら fail-closed)。
負論対照: K80_NO_DEREF_FIX=1 で pass を無効化する。
"""
import argparse
import json
import os
import re

PATCHES = {
    'function_5dee90': [
        ('  %7 = bitcast ptr %r9 to ptr\n', '  %7 = inttoptr i64 %arg4 to ptr\n'),
    ],
    'function_5df040': [
        ('  %7 = bitcast ptr %r9 to ptr\n', '  %7 = inttoptr i64 %arg4 to ptr\n'),
    ],
    'function_5e02b0': [
        ('  %8 = add i64 %arg2, 8\n',
         '  %pbase0 = inttoptr i64 %arg2 to ptr\n'
         '  %base0 = load i64, ptr %pbase0, align 8\n'
         '  %8 = add i64 %arg2, 8\n'),
        ('  %27 = add i64 %13, %arg2\n', '  %27 = add i64 %13, %base0\n'),
    ],
}

RE_FN = re.compile(r'^define [^\n]*@(function_[0-9a-f]+)\(.*?^}\n', re.S | re.M)


def fix(text, rep):
    if os.environ.get('K80_NO_DEREF_FIX') == '1':
        return text, rep
    out = []
    last = 0
    for m in RE_FN.finditer(text):
        name = m.group(1)
        body = m.group(0)
        for old, new in PATCHES.get(name, []):
            n = body.count(old)
            if n != 1:
                raise SystemExit('[FAIL] %s: 置換対象が %d 件 (期待 1): %r' % (name, n, old))
            body = body.replace(old, new)
            rep.setdefault(name, 0)
            rep[name] += 1
        out.append(text[last:m.start()])
        out.append(body)
        last = m.end()
    out.append(text[last:])
    missing = [f for f in PATCHES if f not in {m.group(1) for m in RE_FN.finditer(text)}]
    if missing:
        raise SystemExit('[FAIL] 関数が見つからない: %s' % missing)
    return ''.join(out), rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp')
    ap.add_argument('outp')
    ap.add_argument('--report')
    a = ap.parse_args()
    text = open(a.inp).read()
    rep = {}
    text, rep = fix(text, rep)
    open(a.outp, 'w').write(text)
    if a.report:
        json.dump({'patched': rep}, open(a.report, 'w'), indent=1)
    print('deref_fix: %s' % (rep if rep else 'no-op (K80_NO_DEREF_FIX=1)'))


if __name__ == '__main__':
    main()
