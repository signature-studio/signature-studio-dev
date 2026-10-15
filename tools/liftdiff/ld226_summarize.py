#!/usr/bin/env python3
"""LD-226 (#4590): work/ld226/<条件>.jsonl の verdict と .reset.json の差分を TSV にまとめる。

  python3 ld226_summarize.py > results/ld226_sta_img_stack.tsv
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CONDS = ['sta_img', 'sta_img_deep', 'sta_img_win', 'sta_img_hi', 'all']


def main():
    rows = {}
    diffs = {}
    for c in CONDS:
        for line in open(os.path.join(HERE, 'work', 'ld226', c + '.jsonl')):
            r = json.loads(line)
            rows.setdefault(r['va'], {})[c] = r['verdict']
        diffs[c] = [x[1] for x in json.load(open(os.path.join(HERE, 'work', 'ld226', c + '.jsonl.reset.json')))]
    print('va\t' + '\t'.join(CONDS))
    for va in sorted(rows):
        print(va + '\t' + '\t'.join(rows[va].get(c, '-') for c in CONDS))
    print('reset_diff(first 4 RESET)\t' + '\t'.join(','.join(str(x) for x in diffs[c][:4]) for c in CONDS))


if __name__ == '__main__':
    main()
