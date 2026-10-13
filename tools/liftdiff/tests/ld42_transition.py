"""units と hybrid の batch JSONL から sample の判定遷移を突き合わせる (LD-42 / #1248)。

使い方: python3 tests/ld42_transition.py <units.jsonl> <hybrid.jsonl> [--tsv out.tsv]
出力: 遷移の件数 (from -> to) と、変化した関数 (va / from / to / tags) の TSV。
"""
import collections
import json
import sys


def load(path):
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                d[r['function']['va']] = r
    return d


def tags_of(r):
    if r is None:
        return ''
    s = set()
    for t in r.get('tags', []):
        s.add(t['tag'] if isinstance(t, dict) else str(t))
    return ','.join(sorted(s))


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    tsv = sys.argv[sys.argv.index('--tsv') + 1] if '--tsv' in sys.argv else None
    a, b = load(a_path), load(b_path)
    vas = sorted(set(a) | set(b))
    trans = collections.Counter()
    rows = []
    for va in vas:
        ra, rb = a.get(va), b.get(va)
        va_v = ra['verdict'] if ra else 'missing'
        vb_v = rb['verdict'] if rb else 'missing'
        if va_v != vb_v:
            trans[(va_v, vb_v)] += 1
            rows.append((va, va_v, vb_v, tags_of(rb) or tags_of(ra)))
    print('functions %d changed %d' % (len(vas), len(rows)))
    for (x, y), n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print('  %s -> %s : %d' % (x, y, n))
    if tsv:
        with open(tsv, 'w') as f:
            f.write('va\tunits\thybrid\ttags\n')
            for r in rows:
                f.write('\t'.join(r) + '\n')


if __name__ == '__main__':
    main()
