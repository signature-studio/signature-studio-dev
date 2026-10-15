#!/usr/bin/env python3
"""LD-126 (#2723): work/ld126/<reset>.jsonl (ld126_wasm_state.py の出力) を results/ld126_wasm_state.tsv に集計する。

  python3 ld126_summarize.py > results/ld126_wasm_state.tsv

行 = sample:800 の chunk 1 の 18 関数 (shard 1 の 19 関数のうち chunk 1 に含まれる件。ld121 と同じ)。列 = 候補ごとの verdict。
wasm_restart_ld121 は results/ld121_restart_probe.tsv の wasm 列 (関数ごとに wasm を作り直した参照値)。
"""
import collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONDS = ['none', 'stk', 'sta', 'img', 'all', 'sta_img']


def load(c):
    p = os.path.join(HERE, 'work', 'ld126', c + '.jsonl')
    return [json.loads(l) for l in open(p)]


def main():
    D = collections.OrderedDict()
    for c in CONDS:
        for r in load(c):
            D.setdefault(r['va'], {'name': r['name']})[c] = r['verdict']
    ref = {}
    for l in open(os.path.join(HERE, 'results', 'ld121_restart_probe.tsv')):
        f = l.rstrip('\n').split('\t')
        if f[0] != 'va':
            ref[f[0]] = f[5]
    print('\t'.join(['va', 'name'] + CONDS + ['wasm_restart_ld121']))
    for va, d in sorted(D.items()):
        print('\t'.join([va, d['name']] + [d.get(c, '-') for c in CONDS] + [ref.get(va, '-')]))
    print('# counts (verdict: n) ' + ' '.join('%s=%s' % (c, dict(collections.Counter(d.get(c) for d in D.values()))) for c in CONDS), file=sys.stderr)


if __name__ == '__main__':
    main()
