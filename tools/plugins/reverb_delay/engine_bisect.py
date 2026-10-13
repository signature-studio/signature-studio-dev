#!/usr/bin/env python3
"""RetDec が `[capstone2llvmir]: Should not be possible.` で落ちる engine の原因関数を二分探索で特定する (測定用)。
usage: engine_bisect.py <block> <ranges.txt> <outdir> [timeout_sec=120]
  ranges.txt (engine_ranges.py の出力) を分割し、`retdec-decompiler --select-ranges <subset> --select-decode-only` が .ll を出すかで
  chunk の良/不良を判定する。 不良 chunk は 1 関数になるまで分割 (不良が複数でも全て拾う)。 出力: stdout に不良関数 range と試行回数。
"""
import os, subprocess, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR

blk, rfile, out = sys.argv[1], sys.argv[2], sys.argv[3]
tmo = sys.argv[4] if len(sys.argv) > 4 else '120'
rs = open(rfile).read().strip().split(',')
pe = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % int(blk))
os.makedirs(out, exist_ok=True)
tries = 0
memo = {}


def ok(sub):
    global tries
    key = tuple(sub)
    if key in memo:
        return memo[key]
    tries += 1
    d = os.path.join(out, 'try')
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = subprocess.run(['/opt/retdec/bin/retdec-decompiler', pe, '-o', os.path.join(d, 'x.c'), '--select-ranges', ','.join(sub),
                        '--select-decode-only', '--timeout', tmo], capture_output=True, text=True)
    good = os.path.exists(os.path.join(d, 'x.ll')) or os.path.exists(os.path.join(d, 'x.c.ll'))
    if not good:
        good = any(f.endswith('.ll') for f in os.listdir(d))
    memo[key] = good
    return good


def find(sub):
    if ok(sub):
        return []
    if len(sub) == 1:
        return sub
    m = len(sub) // 2
    return find(sub[:m]) + find(sub[m:])


bad = find(rs)
print('bad_funcs=%d tries=%d of %d ranges' % (len(bad), tries, len(rs)))
for b in bad:
    print(b)
