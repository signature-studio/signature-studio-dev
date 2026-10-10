#!/usr/bin/env python3
"""新旧 boot 状態の flelift 全数 verdict 比較 (CAB-233).
使い方: python3 tests/compare_bootstate.py work/flelift/batch_closure_hybrid.jsonl results/flelift_closure_verdicts.tsv [--md out.md]
"""
import json, sys, collections


def load_new(path):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    out = {}
    for r in recs:
        va = int(r['function']['va'], 16)
        out[va] = (r['verdict'], r.get('unexec_reason') or '', [t['tag'] for t in r.get('tags', [])])
    return out


def load_old(path):
    out = {}
    for line in open(path):
        if line.startswith('#') or not line.strip():
            continue
        p = line.rstrip('\n').split('\t')
        out[int(p[0], 16)] = (p[2], p[5], p[4].split(',') if p[4] else [])
    return out


def main():
    new = load_new(sys.argv[1])
    old = load_old(sys.argv[2])
    md = None
    if '--md' in sys.argv:
        md = sys.argv[sys.argv.index('--md') + 1]
    keys = sorted(set(new) | set(old))
    S = collections.Counter()
    S0 = collections.Counter(vo for vo, _, _ in old.values())
    trans = collections.Counter()
    reasons_new = collections.Counter()
    reasons_old = collections.Counter()
    for k in keys:
        vn, rn, _ = new.get(k, ('?', '', []))
        vo, ro, _ = old.get(k, ('?', '', []))
        S[vn] += 1
        trans[(vo, vn)] += 1
        if vn == 'unexec':
            reasons_new[rn] += 1
        if vo == 'unexec':
            reasons_old[ro] += 1
    lines = []
    lines.append('新 boot 状態: 関数数 %d — 一致 %d / 不一致 %d / 実行不能 %d' % (len(keys), S['match'], S['mismatch'], S['unexec']))
    lines.append('旧 boot 状態 (17 unit):        一致 %d / 不一致 %d / 実行不能 %d' % (S0['match'], S0['mismatch'], S0['unexec']))
    lines.append('')
    lines.append('verdict 遷移 (旧 → 新):')
    for (vo, vn), c in sorted(trans.items(), key=lambda x: -x[1]):
        if vo != vn:
            lines.append('  %-9s → %-9s  %5d' % (vo, vn, c))
    lines.append('')
    lines.append('実行不能 reason 内訳 (新 → 旧):')
    for r in sorted(set(reasons_new) | set(reasons_old), key=lambda x: -(reasons_new.get(x, 0) + reasons_old.get(x, 0))):
        lines.append('  %-34s %5d → %5d' % (r or '-', reasons_new.get(r, 0), reasons_old.get(r, 0)))
    out = '\n'.join(lines)
    print(out)
    if md:
        open(md, 'w').write(out + '\n')


if __name__ == '__main__':
    main()
