#!/usr/bin/env python3
"""dyn_xcheck.py — liftdiff の動的差分 (native vs wasm) 全数採点 (batch_closure.jsonl) を、LSF の site/関数集合と突合する (#510 / LD-10)。
入力: audit_lsf_ssa.py の --json 出力 / liftdiff の batch jsonl (tools/liftdiff/work/m11/batch_closure.jsonl) / 既知の脱落関数 (#484 の 8 関数)
出力: (1) 既知 TRUE_DROP 8 関数に対する動的差分の verdict (= 動的方式の感度の実測)  (2) base 解決不能 169 関数の verdict 分布 (= 動的方式の被覆)
使い方: python3 dyn_xcheck.py SSA.json BATCH.jsonl"""
import collections
import json
import sys

KNOWN = ['5c0270', '41a670', '66e080', '7e5240', '806740', 'c62780', '417b70', '409c80']
ssa = json.load(open(sys.argv[1]))['functions']
rec = {}
for ln in open(sys.argv[2]):
    r = json.loads(ln)
    rec[r['function']['va'][2:]] = r


def outcomes(r):
    return dict(collections.Counter(c['outcome'] for c in r.get('cases', [])))


print('[1] 既知 TRUE_DROP 8 関数 (#484 §3) の動的 verdict')
cnt = collections.Counter()
for v in KNOWN:
    r = rec.get(v)
    vd = r['verdict'] if r else 'absent'
    cnt[vd] += 1
    print('  %-8s %-9s cases=%s tags=%s' % (v, vd, outcomes(r) if r else '-', [t['tag'] for t in r.get('tags', [])] if r else '-'))
print('  集計', dict(cnt), '(分母 8 関数。match/unexec = 動的差分では脱落を見ていない)')
unk = [va for va, r in ssa.items() if any(s['kind'] == 'unk' for s in r['sites'])]
c2 = collections.Counter(rec[v]['verdict'] if v in rec else 'absent' for v in unk)
print('[2] base 解決不能 %d 関数の動的 verdict' % len(unk), dict(c2))
nf = [va for va in unk if any((not s['frame']) and s['kind'] == 'unk' for s in ssa[va]['sites'])]
c3 = collections.Counter(rec[v]['verdict'] if v in rec else 'absent' for v in nf)
print('[3] うち frame 宛でない site を持つ %d 関数' % len(nf), dict(c3))
