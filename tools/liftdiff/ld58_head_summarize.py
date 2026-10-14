#!/usr/bin/env python3
# LD-58 (#1637) の HEAD 再測定の JSONL を results の TSV に変換する (REPORT_APPENDIX_LD58.md §8)。
# usage: python3 ld58_head_summarize.py r1=work/m11/batch_head_r1.jsonl ... --verdict OUT.tsv --cases OUT.tsv
import argparse
import collections
import json

ap = argparse.ArgumentParser()
ap.add_argument('runs', nargs='+', help='label=path.jsonl')
ap.add_argument('--verdict', required=True)
ap.add_argument('--cases', required=True)
a = ap.parse_args()

runs = []
for s in a.runs:
    label, path = s.split('=', 1)
    runs.append((label, [json.loads(l) for l in open(path) if l.strip()]))
labels = [label for label, _ in runs]

names = {}
verdict = collections.defaultdict(dict)
cases = collections.defaultdict(dict)
for label, recs in runs:
    for r in recs:
        va = r['function']['va']
        names[va] = r['function']['name']
        verdict[va][label] = r['verdict']
        for c in r.get('cases', []):
            key = (va, c['pattern'])
            cases[key][label] = '%s(%s/%s)' % (c['outcome'], c['native_status'], c['wasm_status'])

with open(a.verdict, 'w') as f:
    counts = ['%s:%s' % (label, dict(collections.Counter(r['verdict'] for r in recs))) for label, recs in runs]
    f.write('#counts\t' + '\t'.join(counts) + '\n')
    f.write('# va\tname\t' + '\t'.join(labels) + '\n')
    for va in sorted(verdict):
        f.write('%s\t%s\t%s\n' % (va, names[va], '\t'.join(verdict[va].get(label, '-') for label in labels)))

with open(a.cases, 'w') as f:
    f.write('# va\tpattern\t' + '\t'.join(labels) + '\n')
    for va, pat in sorted(cases):
        f.write('%s\t%s\t%s\n' % (va, pat, '\t'.join(cases[(va, pat)].get(label, '-') for label in labels)))
print('wrote', a.verdict, len(verdict), 'functions;', a.cases, len(cases), 'cases')
