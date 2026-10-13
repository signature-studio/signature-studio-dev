"""fault 由来 this 疑似 pattern (fvm) の効果を、2 つの batch JSONL の関数単位遷移として集計する。
使い方: python3 tests/fvm_transitions.py BASE.jsonl NEW.jsonl
既存 pattern (fvm 以外) の case 結果が変わった関数と、verdict の遷移件数を出す。"""
import json, sys, collections


def load(p):
    d = {}
    for l in open(p):
        r = json.loads(l)
        d[r['function']['va']] = r
    return d


def verdict_of(r):
    return r['verdict']


def main(base_p, new_p):
    B, N = load(base_p), load(new_p)
    trans = collections.Counter()
    changed_old = []
    for va in B:
        b, n = B[va], N.get(va)
        if n is None:
            trans['missing'] += 1
            continue
        vb, vn = verdict_of(b), verdict_of(n)
        trans['%s->%s' % (vb, vn)] += 1
        old_b = [(c['pattern'], c['outcome']) for c in b['cases']]
        old_n = [(c['pattern'], c['outcome']) for c in n['cases'] if c['pattern'] != 'fvm']
        if old_b != old_n:
            changed_old.append(va)
    print('TRANSITIONS', dict(sorted(trans.items())))
    print('EXISTING_PATTERN_CHANGED', len(changed_old), changed_old[:20])
    fvm = [(va, c['outcome']) for va in N for c in N[va]['cases'] if c['pattern'] == 'fvm']
    print('FVM_CASES', len(fvm), dict(collections.Counter(o for _, o in fvm)))
    return 1 if changed_old or trans.get('match->mismatch', 0) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
