#!/usr/bin/env python3
"""hostx_e2e.sh の合否判定: batch_lift.sh の status.csv を読み、対象 block が全て合格かを終了コードで返す。
  python3 hostx/judge.py <status.csv> [<block> ...] [-o <out.csv>]
合格条件 (1 行ごと): lift_rc / declares_unimpl / f80_funcs / emcc_c_rc がすべて 0。
  例外: declares_unimpl > 0 でも、未実装 helper の名前 (work/batch/<block>/p.simd.log の `unimplemented:` 行) が全て --allow-unimpl の
  名前集合に入っていれば合格 (既定は空集合 = 例外なし)。 名前が読めない・許可外の名前を含む場合は不合格。
  -1 (batch_lift.sh の「未計測」値) や整数でない値は不合格。 block を指定した場合、その行が無いことも不合格。
  同一 block の行が複数ある場合 (再実行) は最後の行を採用。 -o は採用した行だけを書き出す。
exit: 0 = 全行合格 / 1 = 不合格あり / 2 = 入力不正 (ファイルなし・列欠落・対象行なし)
"""
import argparse
import csv
import os
import re
import sys

CHECKS = ('lift_rc', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc')


def unimpl_names(batch_dir, block):
    """p.simd.log の `unimplemented: void __asm_<name>(...)` 行から名前を取る。 読めなければ None。"""
    try:
        txt = open(os.path.join(batch_dir, block, 'p.simd.log')).read()
    except OSError:
        return None
    return re.findall(r'^\s+unimplemented:.*?__asm_([A-Za-z0-9_]+)\(', txt, re.M)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('status_csv')
    ap.add_argument('blocks', nargs='*')
    ap.add_argument('-o', '--out')
    ap.add_argument('--allow-unimpl', default='', help='許可する未実装 helper 名 (カンマ区切り; 例: rep_stosb_memset)')
    ap.add_argument('--batch-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'batch'))
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
    notes = []
    allow = {x for x in a.allow_unimpl.split(',') if x}
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
            if not ok and c == 'declares_unimpl' and allow and v.isdigit() and int(v) > 0:
                names = unimpl_names(a.batch_dir, b)
                if names and len(names) == int(v) and set(names) <= allow:
                    ok = True
                    notes.append('%s: 許可済み未実装 helper %s' % (b, ','.join(sorted(set(names)))))
            if not ok:
                why.append('%s=%s' % (c, v))
        if why:
            fails.append((b, r[ix['name']], why))

    if a.out:
        with open(a.out, 'w') as f:
            csv.writer(f).writerows([hdr] + body)
    print('judge: rows=%d/%d bad=%d' % (len(body), len(want), len(fails)))
    for n in notes:
        print('  NOTE', n)
    for b, name, why in fails:
        print('  FAIL %s %s: %s' % (b, name, ', '.join(why)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
