#!/usr/bin/env python3
"""lift 準備度の判定 (gate)。 batch_lift.sh の status.csv を読み、対象 block が全て合格でなければ exit 1。

usage: judge.py STATUS_CSV --blocks B1,B2,... [--batch-dir work/batch]
合格条件 (block ごと。 1 つでも欠ければ不合格):
  - status.csv にその block の行がある (再実行で複数行あれば最後の行)
  - lift_rc == 0 / f80_funcs == 0 / emcc_c_rc == 0 / declares_unimpl == 0 (-1 = 集計行なし も不合格)
  - defines == closure_funcs (閉包の関数数と final.ll の define 数が一致 = 関数の脱落・分裂なし)
  - 全列が整数として読める / ヘッダが batch_lift.sh の出力と一致
  - --batch-dir 指定時: <dir>/<block>/p.final.ll の `^define` 数が行の defines と一致し、 p.o が存在して非空
exit: 0 = 全 block 合格 / 1 = 不合格あり / 2 = 入力不正 (ファイル無し・ヘッダ不一致・引数誤り)
"""
import argparse
import csv
import os
import sys

HEADER = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines',
          'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
INTS = [h for h in HEADER if h != 'name']


def judge_row(row, batch_dir=None):
    """行 (dict) を判定し、不合格理由のリストを返す (空 = 合格)。"""
    why = []
    v = {}
    for k in INTS:
        try:
            v[k] = int(row[k])
        except (TypeError, ValueError, KeyError):
            why.append('%s が整数でない (%r)' % (k, row.get(k)))
    if why:
        return why
    if v['lift_rc'] != 0:
        why.append('lift_rc=%d' % v['lift_rc'])
    if v['f80_funcs'] != 0:
        why.append('f80_funcs=%d' % v['f80_funcs'])
    if v['emcc_c_rc'] != 0:
        why.append('emcc_c_rc=%d' % v['emcc_c_rc'])
    if v['declares_unimpl'] != 0:
        why.append('declares_unimpl=%d' % v['declares_unimpl'])
    if v['defines'] != v['closure_funcs']:
        why.append('defines=%d != closure_funcs=%d' % (v['defines'], v['closure_funcs']))
    if batch_dir:
        d = os.path.join(batch_dir, str(v['block']))
        ll, o = os.path.join(d, 'p.final.ll'), os.path.join(d, 'p.o')
        if not os.path.isfile(ll):
            why.append('p.final.ll が無い')
        else:
            n = sum(1 for line in open(ll, errors='replace') if line.startswith('define'))
            if n != v['defines']:
                why.append('p.final.ll の define 数 %d != 行の defines=%d' % (n, v['defines']))
        if not os.path.isfile(o) or os.path.getsize(o) == 0:
            why.append('p.o が無い or 空')
    return why


def main(argv):
    ap = argparse.ArgumentParser(description='lift 準備度の判定 (docstring 参照)')
    ap.add_argument('status_csv')
    ap.add_argument('--blocks', required=True, help='カンマ区切りの block 番号 (重複・空は不可)')
    ap.add_argument('--batch-dir')
    a = ap.parse_args(argv[1:])
    want = [b for b in a.blocks.split(',') if b]
    if not want or len(set(want)) != len(want):
        print('judge: --blocks が空か重複している', file=sys.stderr)
        return 2
    try:
        rows = list(csv.reader(open(a.status_csv)))
    except OSError as e:
        print('judge: %s' % e, file=sys.stderr)
        return 2
    if not rows or rows[0] != HEADER:
        print('judge: ヘッダが想定と違う: %r' % (rows[0] if rows else None), file=sys.stderr)
        return 2
    last = {}
    for r in rows[1:]:
        if len(r) == len(HEADER):
            last[r[0]] = dict(zip(HEADER, r))
        elif r:
            last[r[0]] = {'block': r[0], 'bad_row': r}
    npass = 0
    for b in want:
        row = last.get(b)
        if row is None:
            why = ['status.csv に行が無い']
        elif 'bad_row' in row:
            why = ['列数が %d でない: %r' % (len(HEADER), row['bad_row'])]
        else:
            why = judge_row(row, a.batch_dir)
        npass += not why
        name = row.get('name', '?') if row else '?'
        print('  %-6s %-28s %s' % (b, name, 'PASS' if not why else 'FAIL: ' + '; '.join(why)))
    ok = npass == len(want)
    print('judge: %s %d/%d' % ('PASS' if ok else 'FAIL', npass, len(want)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
