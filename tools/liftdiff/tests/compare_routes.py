#!/usr/bin/env python3
"""compare_routes.py — x64c (flelift) と m11 RetDec route の同一関数での verdict 対応表を作る (CAB-232)。

  python3 tests/compare_routes.py <flelift_batch.jsonl> [m11_tsv] [out_md]

m11 側は results/m11_closure_verdicts.tsv (liftdiff.py export 形式、CAB-231 A/B 以前の RetDec route 全数)。
出力: 4 象限 (両 match / flelift のみ match / flelift のみ mismatch / 両 mismatch) + タグ遷移 + 下位内訳。
"""
import json, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))


def load_flelift(path):
    out = {}
    for l in open(path):
        if not l.strip():
            continue
        r = json.loads(l)
        out[int(r['function']['va'], 16)] = r
    return out


def load_m11(path):
    out = {}
    for l in open(path):
        if l.startswith('#') or not l.strip():
            continue
        f = l.rstrip('\n').split('\t')
        va, name, verdict, prim, tags, reason, pats = f
        out[int(va, 16)] = {'verdict': verdict, 'primary': prim, 'tags': tags, 'patterns': pats}
    return out


def main():
    fle = load_flelift(sys.argv[1])
    m11p = sys.argv[2] if len(sys.argv) > 2 else HERE + '/../results/m11_closure_verdicts.tsv'
    m11 = load_m11(m11p)
    outp = sys.argv[3] if len(sys.argv) > 3 else None
    common = sorted(set(fle) & set(m11))
    q = collections.Counter()
    trans = collections.Counter()
    fle_only_match, fle_only_mismatch = [], []
    fle_unexec, m11_unexec = 0, 0
    for va in common:
        fv, mv = fle[va]['verdict'], m11[va]['verdict']
        q[(fv, mv)] += 1
        if fv == 'match' and mv == 'mismatch':
            fle_only_match.append(va)
        if fv == 'mismatch' and mv == 'match':
            fle_only_mismatch.append(va)
        if fv == 'unexec':
            fle_unexec += 1
        if mv == 'unexec':
            m11_unexec += 1
        # mismatch 同士: m11 主因 → flelift 主因 の遷移
        if fv == 'mismatch' and mv == 'mismatch':
            fp = next((t['tag'] for t in fle[va].get('tags', []) if t['tag']), 'other')
            trans[(m11[va]['primary'], fp)] += 1
    lines = []
    lines.append('共通関数 %d (flelift %d, m11 %d)' % (len(common), len(fle), len(m11)))
    lines.append('')
    lines.append('| m11 \\ flelift | match | mismatch | unexec |')
    lines.append('|---|---|---|---|')
    for mv in ('match', 'mismatch', 'unexec'):
        lines.append('| %s | %d | %d | %d |' % (mv, q[('match', mv)], q[('mismatch', mv)], q[('unexec', mv)]))
    lines.append('')
    both_match = q[('match', 'match')]
    lines.append('- 両 route 一致 (match&match): %d' % both_match)
    lines.append('- flelift のみ一致 (m11 mismatch → match): %d' % q[('match', 'mismatch')])
    lines.append('- flelift のみ不一致 (m11 match → mismatch): %d' % q[('mismatch', 'match')])
    lines.append('- 両方不一致: %d' % q[('mismatch', 'mismatch')])
    lines.append('- 実行不能: m11 %d / flelift %d (flelift は lift 集合外 %d を含む)' % (m11_unexec, fle_unexec, q[('unexec', 'unexec')]))
    lines.append('')
    lines.append('## flelift のみ一致 (m11 mismatch → match) 上位 40')
    for va in fle_only_match[:40]:
        r = fle[va]
        mprim = m11[va]['primary']
        lines.append('- `%x` %s: m11 主因 %s → flelift %s' % (va, r['function']['name'], mprim, ','.join(t['tag'] for t in r.get('tags', [])) or '-'))
    lines.append('')
    lines.append('## flelift のみ不一致 (m11 match → mismatch) 上位 40')
    for va in fle_only_mismatch[:40]:
        r = fle[va]
        ftags = ','.join('%s[%s]' % (t['tag'], t['confidence'][0]) for t in r.get('tags', []))
        lines.append('- `%x` %s: flelift %s' % (va, r['function']['name'], ftags))
    lines.append('')
    lines.append('## 両不一致の主因遷移 (m11 主因 → flelift 主因, 上位 30)')
    for (mp, fp), c in trans.most_common(30):
        lines.append('- %s → %s: %d' % (mp, fp, c))
    text = '\n'.join(lines)
    print(text[:6000])
    if outp:
        open(outp, 'w').write(text + '\n')
        print('wrote', outp)


if __name__ == '__main__':
    main()
