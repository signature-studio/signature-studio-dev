#!/usr/bin/env python3
"""judge.py のネガティブコントロール (NC3)。 実測した status.csv (合格しているもの) を 1 箇所ずつ壊し、CLI の終了コードが非 0 になることを確認する。

  python3 judge_nc.py <status.csv> <block> ...
対照: 無改変の CSV は rc 0。 変異: block ごとに 列 5 種 (lift_rc=1 / f80_funcs=3 / emcc_c_rc=1 / declares_unimpl=5 と -1 / defines=closure_funcs-1 / closure_funcs=defines+1 (どちらも defines < closure_funcs) /
行削除 / 行重複 / 数値でない値 / 要求外 block の行追加) + ファイル全体の変異 (ヘッダのみ / 空 / 不在)。
合格条件 (exit 0): 対照が rc 0 かつ全変異が rc != 0。 受理された変異が 1 つでもあれば exit 1。
"""
import csv, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, 'judge.py')
COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
EXTRA = ['icall', 'dispatch_calls']


FIELDS = COLS


def run(path, want):
    p = subprocess.run([sys.executable, JUDGE, path] + [str(b) for b in want], capture_output=True, text=True)
    return p.returncode


def write(path, rows, cols=None):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, cols or FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    src, want = sys.argv[1], [int(x) for x in sys.argv[2:]]
    global FIELDS
    rd = csv.DictReader(open(src, newline=''))
    FIELDS = rd.fieldnames
    rows = list(rd)
    twelve = FIELDS == COLS + EXTRA
    d = tempfile.mkdtemp(prefix='judge_nc_')
    p = os.path.join(d, 's.csv')
    write(p, rows)
    ctl = run(p, want)
    print('対照 (無改変 %d 行、%d 列): rc=%d (期待 0)' % (len(rows), len(FIELDS), ctl))
    ctl10 = None
    if twelve:       # 12 列 (#539 以降) の CSV から icall / dispatch_calls を落とした 10 列 (#539 以前の形式) も合格する
        with open(p, 'w', newline='') as f:
            w = csv.DictWriter(f, COLS, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)
        ctl10 = run(p, want)
        print('対照 (icall 2 列を落とした 10 列): rc=%d (期待 0)' % ctl10)
        write(p, rows)
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
               ('defines', 'LT'), ('closure_funcs', None), ('closure_funcs', 0), ('seconds', 'x')]
    if twelve:       # 既定鎖 (PLUG_ICALL=1) の測定は本 gate の対象外 → 不合格
        col_mut += [('icall', '1'), ('dispatch_calls', '5'), ('dispatch_calls', 'x')]
    for i, r in enumerate(rows):
        for col, val in col_mut:
            m = [dict(x) for x in rows]
            if val is None:                       # defines < closure_funcs になる値へ
                m[i][col] = str(int(r['defines']) + 1)
            elif val == 0 and col == 'closure_funcs':
                m[i][col] = '0'
            elif val == 'LT':                     # defines = closure_funcs - 1 (閉包関数の数より少ない)
                m[i][col] = str(int(r['closure_funcs']) - 1)
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
    file_mut = [('ヘッダのみ', ','.join(FIELDS) + '\n'), ('空ファイル', ''), ('ヘッダ不正', 'a,b,c\n1,2,3\n')]
    if twelve:       # 11 列 (icall だけ) / 列順入替
        file_mut += [('11 列 (dispatch_calls 欠け)', ','.join(COLS + EXTRA[:1]) + '\n' + ','.join(['1'] * 11) + '\n'),
                     ('12 列だが列順入替', ','.join(COLS + EXTRA[::-1]) + '\n')]
    for label, content in file_mut:
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
    ok = ctl == 0 and acc == 0 and (ctl10 is None or ctl10 == 0)
    print('NC3 judge: %s' % ('DETECTED (全変異を拒否)' if ok else 'NOT DETECTED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
