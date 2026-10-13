#!/usr/bin/env python3
"""work/g1/engines.csv (engine_lift.sh の 1 行サマリ × C++ DLL) の形式検査。 engine の emcc -c rc は参考測定で、合否に使わない。
ただし「全 DLL の行がある / 全列が整数 / RetDec と pass 鎖が走った (lift_rc の値が記録され、define が 1 以上)」は検査し、満たさなければ exit 1 (行欠落や実行失敗を黙って通さない)。
  python3 engine_check.py <engines.csv> <block> ...
"""
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], newline='')))
want = [int(x) for x in sys.argv[2:]]
bad = 0
by = {}
for r in rows:
    by.setdefault(r['block'], []).append(r)
for b in want:
    rs = by.get(str(b), [])
    if len(rs) != 1:
        print('FAIL: engines.csv の block %d の行が %d 個' % (b, len(rs)), file=sys.stderr)
        bad += 1
        continue
    try:
        v = {k: int(x) for k, x in rs[0].items()}
    except (ValueError, TypeError):
        print('FAIL: block %d に整数でない列: %r' % (b, rs[0]), file=sys.stderr)
        bad += 1
        continue
    if v['lift_rc'] < 0 or v['defines'] < 1 or v['pdata_funcs'] < 1:
        print('FAIL: block %d で lift が走っていない: %r' % (b, rs[0]), file=sys.stderr)
        bad += 1
for b in by:
    if b not in {str(w) for w in want}:
        print('FAIL: 要求していない block %s の行' % b, file=sys.stderr)
        bad += 1
print('engine_check: %d/%d DLL の行が妥当 (emcc -c rc は参考値で合否に使わない)' % (len(want) - bad, len(want)))
sys.exit(1 if bad else 0)
