#!/usr/bin/env python3
"""#5069: LB=0 と LB=0x10000 の boot_final.ll の全関数について、本文の差がシフト (整数即値の +LB_DELTA) だけかを判定する。
  usage: m11_lb_ir_shift_check.py A.ll B.ll [out.json]
  関数の列挙と差の有無は m11_lb_ir_fn_diff.py の functions() を使う。差のある関数は、
  行数・骨格 (整数即値を N に置換した行) が一致し、かつ変わった整数の差が全て LB_DELTA のものを shift_only とする。
  それ以外は other として関数名と理由を出す。"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m11_lb_ir_fn_diff import functions  # noqa: E402

LB_DELTA = 0x10000
INT = re.compile(r'(?<![\w%@.])-?\d+(?![\w.])')


def classify(la, lb):
    if len(la) != len(lb):
        return 'line_count_diff'
    for x, y in zip(la, lb):
        if x == y:
            continue
        if INT.sub('N', x) != INT.sub('N', y):
            return 'skeleton_diff'
        for p, q in zip(INT.findall(x), INT.findall(y)):
            if int(p) != int(q) and int(q) - int(p) != LB_DELTA:
                return 'int_delta_%d' % (int(q) - int(p))
    return None


def main():
    a = functions(sys.argv[1])
    b = functions(sys.argv[2])
    names = sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n))
    cls = collections.Counter()
    other = []
    for n in names:
        if n not in a or n not in b:
            cls['only_one_side'] += 1
            other.append({'fn': n, 'why': 'only_one_side'})
            continue
        why = classify(a[n], b[n])
        if why is None:
            cls['shift_only'] += 1
        else:
            cls['other'] += 1
            other.append({'fn': n, 'why': why})
    res = {'functions': len(a), 'differ': len(names), 'lb_delta': LB_DELTA,
           'classes': dict(cls), 'other': other}
    out = json.dumps(res, ensure_ascii=False, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w', encoding='utf-8').write(out)
    print(json.dumps({k: res[k] for k in ('functions', 'differ', 'classes')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
