#!/usr/bin/env python3
"""Gen_Render 差分の判定 (fail-closed)。
 usage: gr_judge.py <native_dir> <wasm_dir> <targets.tsv> [--ulp N]
   <dir>/<block>.bin が results.bin。 判定は shell ごとに
     PASS / PASS-TOL (--ulp 内の差のみ) / DIFF / SHAPE / WASM-ABORT / MISSING-WASM / INVALID-REF (native が基準にならない)
   exit 0 は **全 shell が PASS (または --ulp 指定時の PASS-TOL)** のときだけ。 それ以外・入力不備は exit 1。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gr_lib as L


def main(argv):
    ulp = 0
    if '--ulp' in argv:
        i = argv.index('--ulp')
        ulp = int(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    ndir, wdir, tsv = argv
    rows = [l.rstrip('\n').split('\t') for l in open(tsv) if l.strip()]
    if len(rows) != 12:
        print('[gr_judge] targets が 12 本でない: %d' % len(rows), file=sys.stderr)
        return 1
    ncases = len(L.make_cases())
    cnt = {}
    for blk, name, _va, _isz in rows:
        np_, wp = os.path.join(ndir, blk + '.bin'), os.path.join(wdir, blk + '.bin')
        try:
            nat = L.read_results(np_)
        except (OSError, ValueError) as e:
            v, msg = 'INVALID-REF', 'native 結果を読めない: %s' % e
        else:
            ok, why = L.native_valid(nat, ncases)
            if not ok:
                v, msg = 'INVALID-REF', why
            elif not os.path.exists(wp):
                v, msg = 'MISSING-WASM', 'wasm 結果なし: %s' % wp
            else:
                try:
                    v, det = L.compare(nat, L.read_results(wp), ulp)
                    msg = str(det)
                except ValueError as e:
                    v, msg = 'SHAPE', 'wasm 結果が壊れている: %s' % e
        cnt[v] = cnt.get(v, 0) + 1
        print('%-6s %-16s %-12s %s' % (blk, name, v, msg))
    print('[gr_judge] ' + ' '.join('%s=%d' % kv for kv in sorted(cnt.items())) + ' (ulp<=%d)' % ulp)
    good = cnt.get('PASS', 0) + (cnt.get('PASS-TOL', 0) if ulp else 0)
    if good == len(rows):
        print('[gr_judge] OK 12/12')
        return 0
    print('[gr_judge] FAIL %d/12' % good, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
