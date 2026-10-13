#!/usr/bin/env python3
"""g1_e2e.sh の判定 gate (PLG-G1 / #206)。 batch_lift.sh の status.csv を、要求した block 集合に対して検査する。

  python3 judge.py <status.csv> <block> [<block> ...] [--out FILE]     (--out は全 block 合格のときだけ書く)

block ごとの合格条件 (すべて満たす):
  行がちょうど 1 つ / 列が整数 / closure_funcs > 0 / lift_rc == 0 / emcc_c_rc == 0 / f80_funcs == 0 /
  declares_unimpl == 0 (-1 = simd.log に件数行なし = 不明も不合格) / defines >= closure_funcs
  (RetDec は 1 range から複数 define を出すことがあるため等号にしない。 閉包関数 1 つずつに define があるかは define_audit.py が名前で検査する)
列は 10 列 (#539 以前) または末尾に icall, dispatch_calls を足した 12 列 (#539 以降の batch_lift.sh)。 12 列のときは icall == 0 かつ dispatch_calls == 0 も要求する
(本測定は PLUG_ICALL=0 の鎖。 g1_e2e.sh が固定する。 既定鎖 PLUG_ICALL=1 の status.csv が混ざったら不合格にする)。
要求していない block の行が混ざっていても不合格 (status.csv は e2e が作り直した 1 回分であること)。
終了コード: 全 block 合格のときだけ 0。 1 件でも不合格 / 行不足 / ファイル不在 / 不正な値なら 1 (stderr に理由)。
"""
import csv, sys

COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
EXTRA = ['icall', 'dispatch_calls']      # #539 以降の batch_lift.sh が付ける 2 列 (icall 復元の有無 / p.final.ll の __icall_dispatch 呼出数)
INTS = [c for c in COLS if c != 'name']


def judge(rows, want, has_extra=False):
    """rows: [dict]、want: [int]。 → (不合格理由のリスト, 要求 block 順の行 dict)"""
    fails, by = [], {}
    for r in rows:
        try:
            b = int(r['block'])
        except (KeyError, ValueError, TypeError):
            fails.append((None, 'block 列が整数でない行: %r' % (r,)))
            continue
        by.setdefault(b, []).append(r)
    for b in by:
        if b not in want:
            fails.append((b, '%s: 要求していない block の行がある' % b))
    ok_rows = {}
    for b in want:
        rs = by.get(b, [])
        if len(rs) != 1:
            fails.append((b, '%d: 行が %d 個 (期待 1)' % (b, len(rs))))
            continue
        r = rs[0]
        try:
            v = {c: int(r[c]) for c in INTS}
        except (KeyError, ValueError, TypeError):
            fails.append((b, '%d: 整数でない / 欠けた列: %r' % (b, r)))
            continue
        ok_rows[b] = r
        if has_extra:
            try:
                x = {c: int(r[c]) for c in EXTRA}
            except (KeyError, ValueError, TypeError):
                fails.append((b, '%d: icall / dispatch_calls が整数でない / 欠けた列: %r' % (b, r)))
                continue
            if x['icall'] != 0:
                fails.append((b, '%d: icall=%d (本測定は PLUG_ICALL=0 = 復元前の鎖。 既定鎖 PLUG_ICALL=1 の測定は REPORT §6.1)' % (b, x['icall'])))
            if x['dispatch_calls'] != 0:
                fails.append((b, '%d: dispatch_calls=%d (復元前の鎖では 0 のはず)' % (b, x['dispatch_calls'])))
        if v['closure_funcs'] <= 0:
            fails.append((b, '%d: closure_funcs=%d (> 0 が必要)' % (b, v['closure_funcs'])))
        if v['lift_rc'] != 0:
            fails.append((b, '%d: lift_rc=%d' % (b, v['lift_rc'])))
        if v['emcc_c_rc'] != 0:
            fails.append((b, '%d: emcc_c_rc=%d' % (b, v['emcc_c_rc'])))
        if v['f80_funcs'] != 0:
            fails.append((b, '%d: f80_funcs=%d' % (b, v['f80_funcs'])))
        if v['declares_unimpl'] != 0:
            fails.append((b, '%d: declares_unimpl=%d (-1 は件数行なし)' % (b, v['declares_unimpl'])))
        if v['defines'] < v['closure_funcs']:
            fails.append((b, '%d: defines=%d < closure_funcs=%d' % (b, v['defines'], v['closure_funcs'])))
    return fails, ok_rows


def load(path):
    with open(path, newline='') as f:
        rd = csv.DictReader(f)
        if rd.fieldnames not in (COLS, COLS + EXTRA):
            raise ValueError('ヘッダが想定と違う (10 列 %r、または末尾に %r を足した 12 列): %r' % (COLS, EXTRA, rd.fieldnames))
        return rd.fieldnames, list(rd)


def main(argv):
    out = None
    if '--out' in argv:
        i = argv.index('--out')
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        want = [int(x) for x in argv[1:]]
        fieldnames, rows = load(argv[0])
    except Exception as e:  # ファイル不在・ヘッダ不正も不合格
        print('FAIL: status.csv を読めない: %s' % e, file=sys.stderr)
        return 1
    fails, ok_rows = judge(rows, want, fieldnames == COLS + EXTRA)
    if out and not fails:          # 不合格のときは成果物を書かない (前回の合格済み出力を壊さない)
        with open(out, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames)
            w.writeheader()
            for b in want:
                if b in ok_rows:
                    w.writerow(ok_rows[b])
    bad_blocks = {b for b, _ in fails if b in want}
    print('judge: %d/%d block 合格, 不合格理由 %d 件 (lift_rc==0 / emcc_c_rc==0 / f80==0 / declares_unimpl==0 / defines>=closure_funcs)' % (
        len(want) - len(bad_blocks), len(want), len(fails)))
    for b, m in fails:
        print('FAIL: %s' % m, file=sys.stderr)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
