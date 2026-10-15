#!/usr/bin/env python3
"""#3229: 2 つの IR (.ll) を関数単位で比べる (LB 別の boot_final.ll の切り分け用)。
  usage: m11_lb_ir_fn_diff.py A.ll B.ll [function_name ...]
  関数名を省略すると、本文が違う関数を全て列挙する。関数名を与えると、その関数の本文の unified diff と、
  差分行に現れる整数即値 (LB に依存しうる VA・LVA) を出す。本文の一致は差 0 として扱う。"""
import difflib
import json
import re
import sys

DEF = re.compile(r'^define\b[^@]*@([^\s(]+)\(')
IMM = re.compile(r'(?<![\w%@.])-?\d{4,}(?![\w.])')


def functions(path):
    out = {}
    name = None
    buf = []
    for line in open(path, encoding='utf-8', errors='replace'):
        if name is None:
            m = DEF.match(line)
            if m:
                name = m.group(1)
                buf = [line]
            continue
        buf.append(line)
        if line.startswith('}'):
            out[name] = buf
            name = None
    return out


def main():
    a = functions(sys.argv[1])
    b = functions(sys.argv[2])
    if len(sys.argv) <= 3:
        diff_names = sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n))
        print(json.dumps({'functions_a': len(a), 'functions_b': len(b), 'differ': len(diff_names), 'names': diff_names}, ensure_ascii=False))
        return
    for n in sys.argv[3:]:
        if n not in a or n not in b:
            print(json.dumps({'fn': n, 'only_in': 'A' if n in a else 'B' if n in b else 'none'}))
            continue
        if a[n] == b[n]:
            print(json.dumps({'fn': n, 'differ': False, 'lines': len(a[n])}))
            continue
        d = [l.rstrip('\n') for l in difflib.unified_diff(a[n], b[n], 'A', 'B', n=0)]
        changed = [l for l in d if l[:1] in '+-' and l[:3] not in ('+++', '---')]
        imms = sorted({m for l in changed for m in IMM.findall(l)})
        print(json.dumps({'fn': n, 'differ': True, 'lines_a': len(a[n]), 'lines_b': len(b[n]), 'changed_lines': len(changed), 'imms_in_changed': imms}, ensure_ascii=False))
        print('\n'.join(d[:200]))


if __name__ == '__main__':
    main()
