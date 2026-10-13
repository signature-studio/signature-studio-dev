#!/usr/bin/env python3
"""dynamics_e2e.sh の合否判定: batch_lift.sh の status.csv を読み、対象 block が全て合格かを終了コードで返す。
  python3 dynamics/judge.py <status.csv> [<block> ...] [-o <out.csv>]
合格条件 (1 行ごと): lift_rc / declares_unimpl / f80_funcs / emcc_c_rc がすべて 0。
  -1 (batch_lift.sh の「未計測」値) や整数でない値は不合格。 block を指定した場合、その行が無いことも不合格。
  同一 block の行が複数ある場合 (再実行) は最後の行を採用。 -o は採用した行だけを書き出す。
exit: 0 = 全行合格 / 1 = 不合格あり / 2 = 入力不正 (ファイルなし・列欠落・対象行なし)
"""
import argparse
import csv
import sys

CHECKS = ('lift_rc', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('status_csv')
    ap.add_argument('blocks', nargs='*')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()

    try:
        with open(a.status_csv, newline='') as f:
            rows = list(csv.reader(f))
    except OSError as e:
        print('judge: cannot read %s: %s' % (a.status_csv, e), file=sys.stderr)
        return 2
    if not rows:
        print('judge: empty csv: %s' % a.status_csv, file=sys.stderr)
        return 2
    hdr = rows[0]
    missing = [c for c in ('block', 'name') + CHECKS if c not in hdr]
    if missing:
        print('judge: columns missing in header: %s' % ','.join(missing), file=sys.stderr)
        return 2
    ix = {c: hdr.index(c) for c in hdr}

    last = {}
    for r in rows[1:]:
        if len(r) == len(hdr):
            last[r[ix['block']]] = r
    want = a.blocks or list(last)
    if not want:
        print('judge: no data rows: %s' % a.status_csv, file=sys.stderr)
        return 2
    body = [last[b] for b in want if b in last]

    fails = []
    for b in want:
        r = last.get(b)
        if r is None:
            fails.append((b, '?', ['no row']))
            continue
        why = []
        for c in CHECKS:
            v = r[ix[c]].strip()
            try:
                ok = int(v) == 0
            except ValueError:
                ok = False
            if not ok:
                why.append('%s=%s' % (c, v))
        if why:
            fails.append((b, r[ix['name']], why))

    if a.out:
        with open(a.out, 'w') as f:
            csv.writer(f).writerows([hdr] + body)
    print('judge: rows=%d/%d bad=%d' % (len(body), len(want), len(fails)))
    for b, name, why in fails:
        print('  FAIL %s %s: %s' % (b, name, ', '.join(why)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
