#!/usr/bin/env python3
"""閉包の関数 1 つずつに lift 後 IR の define があるかを名前 (function_<開始 VA>) で検査する (PLG-G1 / #206)。
  python3 define_audit.py [--batch-dir DIR] <block> ...     (DIR/<block>/p.final.ll を読む。 既定 work/batch。 ネガティブコントロール用)
  ranges = work/closure/block*.ranges.txt の各 range の開始 VA、 define = work/batch/<block>/p.final.ll の `define @function_<VA>`。
  missing = range 開始 VA に define が無い数 (> 0 なら exit 1: 関数が IR から落ちている)。
  extra   = range 開始 VA 以外の define 数 (RetDec が range 内部に切り出した関数。 許容して件数と所在を報告する; 範囲外に出たものは unexpected として exit 1)。
  ranges / final.ll が無い・空の block も exit 1。
"""
import os, re, sys
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work')
a = sys.argv[1:]
batch = os.path.join(W, 'batch')
if a[:1] == ['--batch-dir']:
    batch, a = a[1], a[2:]
bad = 0
print('| block | ranges | define (function_*) | missing | extra (range 内部) | unexpected (range 外) |')
print('|--:|--:|--:|--:|--:|--:|')
for b in map(int, a):
    try:
        rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)).read().replace(',', '\n').split()]
        ll = open(os.path.join(batch, str(b), 'p.final.ll')).read()
    except OSError as e:
        print('FAIL: block %d: %s' % (b, e), file=sys.stderr)
        bad += 1
        continue
    defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
    starts = {a for a, _ in rg}
    missing = starts - defs
    extra = defs - starts
    inside = {x for x in extra if any(a <= x <= e for a, e in rg)}
    unexpected = extra - inside
    print('| %d | %d | %d | %d | %d | %d |' % (b, len(rg), len(defs), len(missing), len(inside), len(unexpected)))
    if not rg or missing or unexpected:
        print('FAIL: block %d: ranges=%d missing=%s unexpected=%s' % (b, len(rg), sorted(hex(x) for x in missing), sorted(hex(x) for x in unexpected)), file=sys.stderr)
        bad += 1
print('define_audit: 不合格 block = %d' % bad)
sys.exit(1 if bad else 0)
