#!/usr/bin/env python3
"""PLG-F7 (#204) lift 判定 gate。 batch_lift.sh の status.csv を読み、対象 block が全て合格でなければ非 0 で終わる。

usage: judge.py <status.csv> <block> [<block> ...] [--since-line N] [--out normalized.csv]
       judge.py --engines <engines.csv> <expected.csv>

shell 判定 (1 block あたり、全て満たすこと):
  行がある / closure_funcs > 0 / lift_rc == 0 / defines == closure_funcs / declares_unimpl == 0 / f80_funcs == 0 / emcc_c_rc == 0
  (-1 は「測れていない」ので不合格。 同一 block の行が複数なら最後の行)
--since-line N : status.csv の N 行目 (1 始まり、ヘッダ = 1 行目) 以前の行を無視する (前回実行の合格行で今回の失敗を隠さないため)
--engines      : C++ module の測定行 (engines.csv) が expected.csv の全列と一致するか (drift 検出)。 不一致・欠落は不合格

終了コード: 0 = 全て合格 / 1 = 不合格 (理由を全件表示) / 2 = 入力不正 (ファイル無し・列欠落・数値でない・対象 block 無し)
"""
import csv
import sys

NEED = ['block', 'name', 'closure_funcs', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc']


def die(msg):
    print('judge: 入力不正: %s' % msg, file=sys.stderr)
    sys.exit(2)


def read_rows(path, since=1):
    try:
        lines = open(path, newline='').read().splitlines()
    except OSError as e:
        die('%s を開けない (%s)' % (path, e))
    if not lines:
        die('%s が空' % path)
    hdr = next(csv.reader([lines[0]]))
    body = [r for r in csv.reader(lines[max(since, 1):]) if r]
    return hdr, body


def shell_gate(path, blocks, since, out):
    hdr, body = read_rows(path, since)
    miss = [c for c in NEED if c not in hdr]
    if miss:
        die('status.csv に列が無い: %s' % miss)
    ix = {c: hdr.index(c) for c in hdr}
    last = {}
    for r in body:
        if len(r) != len(hdr):
            die('列数が不正な行: %r' % r)
        last[r[ix['block']]] = r
    fails = 0
    kept = []
    for b in blocks:
        r = last.get(b)
        if r is None:
            fails += 1
            print('FAIL %s: status 行が無い (lift が走っていない / 途中で落ちた)' % b)
            continue
        kept.append(r)
        try:
            v = {c: int(r[ix[c]]) for c in NEED if c not in ('block', 'name')}
        except ValueError:
            die('数値でない値: %r' % r)
        why = []
        if v['closure_funcs'] <= 0:
            why.append('closure_funcs=%d' % v['closure_funcs'])
        if v['lift_rc'] != 0:
            why.append('lift_rc=%d' % v['lift_rc'])
        if v['defines'] != v['closure_funcs']:
            why.append('defines=%d != closure_funcs=%d' % (v['defines'], v['closure_funcs']))
        if v['declares_unimpl'] != 0:
            why.append('declares_unimpl=%d' % v['declares_unimpl'])
        if v['f80_funcs'] != 0:
            why.append('f80_funcs=%d' % v['f80_funcs'])
        if v['emcc_c_rc'] != 0:
            why.append('emcc_c_rc=%d' % v['emcc_c_rc'])
        if why:
            fails += 1
        print('%s %s %-18s %s' % ('FAIL' if why else 'PASS', b, r[ix['name']], '; '.join(why)))
    if out:
        with open(out, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(hdr)
            w.writerows(kept)
    print('judge: %d/%d block 合格' % (len(blocks) - fails, len(blocks)))
    return 1 if fails else 0


def engines_gate(path, exp_path):
    hdr, body = read_rows(path)
    ehdr, ebody = read_rows(exp_path)
    if hdr[0] != 'block' or ehdr[0] != 'block':
        die('engines.csv / expected.csv の先頭列は block')
    got = {r[0]: dict(zip(hdr, r)) for r in body}
    fails = 0
    for r in ebody:
        e = dict(zip(ehdr, r))
        g = got.get(e['block'])
        if g is None:
            fails += 1
            print('FAIL %s: 測定行が無い' % e['block'])
            continue
        diff = ['%s: expected %s got %s' % (c, e[c], g.get(c)) for c in ehdr if g.get(c) != e[c]]
        if diff:
            fails += 1
        print('%s %s %s' % ('FAIL' if diff else 'PASS', e['block'], '; '.join(diff)))
    print('judge --engines: %d/%d module が期待列と一致' % (len(ebody) - fails, len(ebody)))
    return 1 if fails else 0


def main():
    a = sys.argv[1:]
    if a and a[0] == '--engines':
        if len(a) != 3:
            die('usage: judge.py --engines <engines.csv> <expected.csv>')
        sys.exit(engines_gate(a[1], a[2]))
    since, out, pos = 1, None, []
    i = 0
    while i < len(a):
        if a[i] == '--since-line':
            since = int(a[i + 1]); i += 2
        elif a[i] == '--out':
            out = a[i + 1]; i += 2
        else:
            pos.append(a[i]); i += 1
    if len(pos) < 2:
        die('usage: judge.py <status.csv> <block> [<block> ...] [--since-line N] [--out f]')
    sys.exit(shell_gate(pos[0], pos[1:], since, out))


if __name__ == '__main__':
    main()
