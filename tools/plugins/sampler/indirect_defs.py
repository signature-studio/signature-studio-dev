#!/usr/bin/env python3
"""推移閉包の ranges の全関数が lift 後の final.ll に `define @function_<開始 VA>` として残っているかを監査する (#537)。
judge.py の `defines>0` は「何か 1 つ lift できた」ことしか言わないので、range 単位の欠落をここで不合格にする。
usage: indirect_defs.py [--lift-dir DIR] [--ranges-dir DIR]     欠落が 1 件でもあれば exit 1。 対象 block は targets.py
出力: 1 block 1 行 (ranges 数 / define あり / 欠落 / range 内部に増えた define)
"""
import argparse, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
import targets

ap = argparse.ArgumentParser()
ap.add_argument('--lift-dir', default=os.path.join(P, 'work', 'sampler', 'indirectlift'))
ap.add_argument('--ranges-dir', default=os.path.join(P, 'work', 'sampler', 'indirect'))
a = ap.parse_args()
bad = 0
for name, blk, _ in targets.SHELLS:
    try:
        rs = open(os.path.join(a.ranges_dir, 'block%05d.ranges.txt' % blk)).read().strip().split(',')
        ll = open(os.path.join(a.lift_dir, str(blk), 'p.final.ll')).read()
    except OSError as e:
        print('FAIL %s: 入力を読めない: %s' % (name, e))
        bad += 1
        continue
    want = {int(r.split('-')[0], 16) for r in rs if r}
    have = {int(m.group(1), 16) for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\(', ll, re.M)}
    miss = sorted(want - have)
    extra = len(have - want)
    ok = len(want) > 0 and not miss
    bad += not ok
    print('%s block %d: ranges %d / define あり %d / 欠落 %d / range 内部の追加 define %d%s' % (
        name, blk, len(want), len(want & have), len(miss), extra, '' if ok else '  FAIL ' + ','.join(hex(m) for m in miss[:5])))
print('indirect_defs: %s' % ('FAIL' if bad else 'PASS %d/%d' % (len(targets.SHELLS), len(targets.SHELLS))))
sys.exit(1 if bad else 0)
