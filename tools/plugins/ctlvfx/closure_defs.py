#!/usr/bin/env python3
"""lift 欠落監査 (gate): 閉包の全 range の開始 VA に対応する `define @function_<VA>` が final.ll にあるか。
  usage: closure_defs.py [batch_dir]      (既定 work/batch。 <batch_dir>/<block>/p.final.ll と work/closure/block<N>.ranges.txt を読む)
  missing      = range の開始 VA に define が無い数。 1 つでもあれば exit 1 (関数が lift 結果から脱落している = 呼出側が link 時に未解決)
  extra_inside = range 開始 VA でない define のうち range 内部に入るもの (RetDec が 1 range を複数 define に切る。 正常な挙動として許容)
  outside      = range の開始でも内部でもない define (閉包外の関数が混入)。 1 つでもあれば exit 1
  final.ll が無い plugin も不合格。
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from targets import TARGETS
P = os.path.join(HERE, '..')
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'batch')
bad = 0
print('%-28s %6s %7s %7s %7s %7s' % ('plugin', 'ranges', 'defines', 'missing', 'extra', 'outside'))
for name, blk, _tier, _eng in TARGETS:
    rf = os.path.join(P, 'work', 'closure', 'block%05d.ranges.txt' % blk)
    lf = os.path.join(B, str(blk), 'p.final.ll')
    if not (os.path.exists(rf) and os.path.exists(lf)):
        bad += 1
        print('%-28s final.ll / ranges が無い  NG' % name)
        continue
    rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(rf).read().strip().split(',')]
    ll = open(lf).read()
    defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
    starts = {a for a, _ in rg}
    missing = starts - defs
    extra = {x for x in defs - starts if any(a <= x <= e for a, e in rg)}
    outside = defs - starts - extra
    ng = bool(missing or outside)
    bad += ng
    print('%-28s %6d %7d %7d %7d %7d  %s' % (name, len(rg), len(defs), len(missing), len(extra), len(outside), 'NG' if ng else 'OK'))
print('closure_defs: %d/%d プラグインで脱落・混入なし' % (len(TARGETS) - bad, len(TARGETS)))
sys.exit(1 if bad else 0)
