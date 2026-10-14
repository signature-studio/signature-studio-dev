#!/usr/bin/env python3
"""spill_classify_1161.py — #1161 (LD-35) spill 宛 178 site の分類表と脱落関数の和集合。

入力: audit_lsf_ssa.py --json の出力 (ssa.json) / 目視判定 manual_verdicts_510.jsonl / 候補判定 candidate_verdicts_1161.jsonl・candidate_verdicts_2245.jsonl・candidate_verdicts_2838.jsonl・candidate_verdicts_2921.jsonl・candidate_verdicts_2922.jsonl
出力: 第 2 引数の TSV (既定 results/spill178_1161.tsv・site ごとに 1 行) と標準出力の集計

status:
  確定   = 目視 (510) または候補判定 (1161) で TRUE_DROP / OK_LOAD / NO_CONSUMER と判定済み
  判定不能 = 候補判定で UNDETERMINED (根拠不足)
  未判定 = どちらの判定も無い (oracle 結果のみ)
脱落関数 = drops_510.tsv の store 宛 ∪ frame 宛 (標準出力 [5]) と、spill 宛の確定 TRUE_DROP のうち [5] に無いもの (標準出力 [6])。候補の未判定は含めない。両者の和集合 = [5] の件数 + [6] の件数。
使い方: python3 spill_classify_1161.py SSA.json [OUT.tsv]
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ssa = json.load(open(sys.argv[1]))['functions']


def load(path):
    out = {}
    for ln in open(os.path.join(HERE, path)):
        r = json.loads(ln)
        out[(r['fn'], r['site'])] = r['verdict']
    return out


man = load('results/manual_verdicts_510.jsonl')
cand = load('results/candidate_verdicts_1161.jsonl')
cand.update(load('results/candidate_verdicts_2245.jsonl'))
cand.update(load('results/candidate_verdicts_2838.jsonl'))
cand.update(load('results/candidate_verdicts_2921.jsonl'))
cand.update(load('results/candidate_verdicts_2922.jsonl'))
TSV = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'results/spill178_1161.tsv')

rows = []
for v, r in ssa.items():
    for s in r['sites']:
        if s['kind'] == 'unk' and s['frame']:
            key = (v, s['addr'])
            if key in man:
                src, verdict = 'manual', man[key]
            elif key in cand:
                src, verdict = 'cand', cand[key]
            else:
                src, verdict = '-', ''
            if verdict == 'UNDETERMINED':
                status = '判定不能'
            elif verdict:
                status = '確定'
            else:
                status = '未判定'
            oracle = s['cell']['verdict'] if s.get('cell') else '-'
            rows.append((v, s['addr'], src, verdict, status, oracle, s['text']))
rows.sort(key=lambda x: (int(x[0], 16), int(x[1], 16)))

with open(TSV, 'w') as f:
    f.write('fn\tsite\tsource\tverdict\tstatus\toracle\ttext\n')
    for row in rows:
        f.write('\t'.join(row) + '\n')

print('[1] spill 宛 unk site: %d site / %d 関数' % (len(rows), len({r[0] for r in rows})))
print('[2] status:', dict(collections.Counter(r[4] for r in rows)))
print('[3] verdict (source):', dict(sorted(collections.Counter((r[3] or '-') + '(' + r[2] + ')' for r in rows).items())))
print('[4] oracle x status:', dict(sorted(collections.Counter(r[5] + '/' + r[4] for r in rows).items())))

drops = [ln.rstrip('\n').split('\t') for ln in open(os.path.join(HERE, 'results/drops_510.tsv'))][1:]
store_fn = {d[0] for d in drops if d[2] == 'store'}
frame_fn = {d[0] for d in drops if d[2] == 'frame'}
union = store_fn | frame_fn
spill_true = {r[0] for r in rows if r[3] == 'TRUE_DROP'}
print('[5] drops_510.tsv: store 宛 DROP 関数 %d / spill 宛 (目視+候補) 関数 %d / 和集合 %d' % (len(store_fn), len(frame_fn), len(union)))
print('[6] spill 宛の確定 TRUE_DROP 関数 %d。うち drops_510 に無いもの: %s' % (
    len(spill_true), ' '.join(sorted(spill_true - union, key=lambda x: int(x, 16))) or '無し'))
print('    spill 宛 未判定 (oracle 候補無し) の関数 %d は和集合に含めていない' % len({r[0] for r in rows if r[4] == '未判定'} - union))
