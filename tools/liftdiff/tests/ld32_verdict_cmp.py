# LD-32 (#1070): sample:800 の n 回 batch (jsonl) を関数単位で突き合わせる。
# 使い方: python3 tests/ld32_verdict_cmp.py r1.jsonl r2.jsonl r3.jsonl > verdict.tsv
# 出力: verdict が run 間で変わった関数と、case outcome が変わった pattern を列挙する (変化 0 件なら 1 行目のみ)。
import json, sys

def load(p):
    d = {}
    for l in open(p):
        j = json.loads(l)
        d[j['function']['va']] = (j['verdict'], {c['pattern']: c['outcome'] for c in j['cases']})
    return d

runs = [load(p) for p in sys.argv[1:]]
print('#va\t' + '\t'.join('verdict_r%d' % (i + 1) for i in range(len(runs))) + '\tcase_outcome_changed_patterns')
for va in sorted(runs[0]):
    vs = [r[va][0] for r in runs]
    ch = []
    for p in sorted(set().union(*[r[va][1].keys() for r in runs])):
        o = [r[va][1].get(p, '-') for r in runs]
        if len(set(o)) > 1:
            ch.append('%s=%s' % (p, '|'.join(o)))
    if ch or len(set(vs)) > 1:
        print('%s\t%s\t%s' % (va, '\t'.join(vs), ' '.join(ch)))
