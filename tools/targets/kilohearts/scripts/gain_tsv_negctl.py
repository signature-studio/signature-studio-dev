#!/usr/bin/env python3
"""verify_gain_tsv.py のネガティブコントロール (KH-19f, #1816).

TSV を 1 件だけ壊した 2 ファイルを作る (元 TSV は変更しない)。
 neg_A.tsv: root 行 (最初の 1 件) の root_class を BogusDsp に置換 → 検査 A が 1 件 FAIL すること
 neg_B.tsv: 非 root 行 (最初の 1 件) の call_site_rva を +1 → 検査 B が 1 件 FAIL すること
usage: gain_tsv_negctl.py <gain_before_160.tsv> <outdir>
"""
import sys, csv, os


def main(tsvp, outdir):
    rows = list(csv.reader(open(tsvp), delimiter='\t'))
    h = rows[0]
    ri, ci = h.index('root_class'), h.index('call_site_rva')
    os.makedirs(outdir, exist_ok=True)

    out = [h] + [list(r) for r in rows[1:]]
    for r in out[1:]:
        if r[ri]:
            r[ri] = 'BogusDsp'
            print('neg_A: root row func_rva', r[h.index('func_rva')])
            break
    csv.writer(open(os.path.join(outdir, 'neg_A.tsv'), 'w', newline=''), delimiter='\t').writerows(out)

    out = [h] + [list(r) for r in rows[1:]]
    for r in out[1:]:
        if not r[ri]:
            r[ci] = hex(int(r[ci], 16) + 1)
            print('neg_B: non-root row func_rva', r[h.index('func_rva')])
            break
    csv.writer(open(os.path.join(outdir, 'neg_B.tsv'), 'w', newline=''), delimiter='\t').writerows(out)


if __name__ == '__main__':
    main(*sys.argv[1:3])
