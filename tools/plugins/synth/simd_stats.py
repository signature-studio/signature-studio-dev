#!/usr/bin/env python3
"""m11_simd2 のログ (`[simd2] declares N: implemented X, unimplemented Y, i256 trap Z`) から "Y Z" を出力する。
ログ or 該当行が無ければ "-1 -1" (judge は -1 を不合格とする)。 usage: simd_stats.py <*.simd.log>
"""
import re, sys
try:
    m = re.search(r'declares (\d+): implemented (\d+), unimplemented (\d+), i256 trap (\d+)', open(sys.argv[1]).read())
except OSError:
    m = None
print('%s %s' % (m.group(3), m.group(4)) if m else '-1 -1')
