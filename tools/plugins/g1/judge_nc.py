#!/usr/bin/env python3
"""judge.py のネガティブコントロール (NC3)。 実測した status.csv (合格しているもの) を 1 箇所ずつ壊し、CLI の終了コードが非 0 になることを確認する。

  python3 judge_nc.py <status.csv> <block> ...
対照: 無改変の CSV は rc 0。 変異: block ごとに 列 5 種 (lift_rc=1 / f80_funcs=3 / emcc_c_rc=1 / declares_unimpl=5 と -1 / defines-1 / closure_funcs+defines+1 (defines < closure_funcs になる) /
行削除 / 行重複 / 数値でない値 / 要求外 block の行追加) + ファイル全体の変異 (ヘッダのみ / 空 / 不在)。
合格条件 (exit 0): 対照が rc 0 かつ全変異が rc != 0。 受理された変異が 1 つでもあれば exit 1。
"""
import csv, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, 'judge.py')
COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']


def run(path, want):
    p = subprocess.run([sys.executable, JUDGE, path] + [str(b) for b in want], capture_output=True, text=True)
    return p.returncode


def write(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)


def main():
    src, want = sys.argv[1], [int(x) for x in sys.argv[2:]]
    rows = list(csv.DictReader(open(src, newline='')))
    d = tempfile.mkdtemp(prefix='judge_nc_')
    p = os.path.join(d, 's.csv')
    write(p, rows)
    ctl = run(p, want)
    print('対照 (無改変 %d 行): rc=%d (期待 0)' % (len(rows), ctl))
    n = acc = 0
    accepted = []

    def check(label, rs):
        nonlocal n, acc
        write(p, rs)
        rc = run(p, want)
        n += 1
        if rc == 0:
            acc += 1
            accepted.append(label)

    # (列, 値)。 値が int なら現値への加算
    col_mut = [('lift_rc', '1'), ('f80_funcs', '3'), ('emcc_c_rc', '1'), ('declares_unimpl', '5'), ('declares_unimpl', '-1'),
               ('defines', -1), ('closure_funcs', None), ('closure_funcs', 0), ('seconds', 'x')]
    for i, r in enumerate(rows):
        for col, val in col_mut:
            m = [dict(x) for x in rows]
            if val is None:                       # defines < closure_funcs になる値へ
                m[i][col] = str(int(r['defines']) + 1)
            elif val == 0 and col == 'closure_funcs':
                m[i][col] = '0'
            elif isinstance(val, int):
                m[i][col] = str(int(r[col]) + val)
            else:
                m[i][col] = val
            check('%s %s=%s' % (r['block'], col, m[i][col]), m)
        check('%s 行削除' % r['block'], [dict(x) for j, x in enumerate(rows) if j != i])
        check('%s 行重複' % r['block'], [dict(x) for x in rows] + [dict(r)])
    ex = dict(rows[0]); ex['block'] = '99999'
    check('要求外 block 99999 の行追加', [dict(x) for x in rows] + [ex])
    n_row = n
    # ファイル全体の変異
    for label, content in (('ヘッダのみ', ','.join(COLS) + '\n'), ('空ファイル', ''), ('ヘッダ不正', 'a,b,c\n1,2,3\n')):
        open(p, 'w').write(content)
        rc = run(p, want)
        n += 1
        if rc == 0:
            acc += 1
            accepted.append(label)
    rc = run(os.path.join(d, 'nonexistent.csv'), want)
    n += 1
    if rc == 0:
        acc += 1
        accepted.append('ファイル不在')
    print('変異 %d 件 (行/列 %d + ファイル全体 %d): 受理 %d / 拒否 %d' % (n, n_row, n - n_row, acc, n - acc))
    for a in accepted:
        print('  ACCEPTED (NOT DETECTED):', a)
    ok = ctl == 0 and acc == 0
    print('NC3 judge: %s' % ('DETECTED (全変異を拒否)' if ok else 'NOT DETECTED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
