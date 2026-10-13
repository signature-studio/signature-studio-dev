#!/usr/bin/env python3
"""synth_e2e.sh の判定 (lift 前提の合否)。 不合格があれば **exit 1** (表示だけで 0 を返さない)。

usage: judge.py <status.csv> [--known known.json] [--strict] [--want BLOCK ...]

合格条件 (1 行 = 1 モジュール): 次の列がすべて 0、かつ defines > 0
  lift_rc / declares_unimpl / i256_trap / f80_funcs / emcc_c_rc / missing_define       (-1 = 出力欠落の印 → 不合格)
判定の種類:
  PASS      全条件を満たす (known.json に載っていない)
  KNOWN     不合格だが known.json の fails と完全に一致 (起票先 ref 付きの既知欠陥)
  NEW-FAIL  known.json に無い不合格が出た                       → exit 1
  FIXED     known.json に載っている不合格が解消した (要 baseline 更新) → exit 1
  MISSING   --want のブロックに行が無い / 重複 / 数値でない        → exit 1
--strict は known.json を無視する (KNOWN も不合格として exit 1)。
"""
import argparse, csv, json, os, sys

COLS = ['lift_rc', 'declares_unimpl', 'i256_trap', 'f80_funcs', 'emcc_c_rc', 'missing_define']


def fails_of(row):
    f = []
    for c in COLS:
        if int(row[c]) != 0:
            f.append(c)
    if int(row['defines']) <= 0:
        f.append('defines')
    return f


def judge(rows, known, want, strict=False):
    """returns (verdicts: list[(block, name, kind, fails)], ok: bool)"""
    out, ok = [], True
    seen = {}
    for r in rows:
        seen.setdefault(r['block'], []).append(r)
    blocks = [str(b) for b in want] if want else list(seen)
    for b in blocks:
        rs = seen.get(b, [])
        if len(rs) != 1:
            out.append((b, '?', 'MISSING', ['rows=%d' % len(rs)]))
            ok = False
            continue
        r = rs[0]
        try:
            f = fails_of(r)
        except (ValueError, KeyError) as e:
            out.append((b, r.get('name', '?'), 'MISSING', ['malformed:%s' % e]))
            ok = False
            continue
        exp = [] if strict else sorted((known.get(b) or {}).get('fails', []))
        if not f and not exp:
            kind = 'PASS'
        elif sorted(f) == exp:
            kind = 'KNOWN'
        elif set(f) - set(exp):
            kind = 'NEW-FAIL'
        else:
            kind = 'FIXED'
        if kind not in ('PASS', 'KNOWN'):
            ok = False
        out.append((b, r['name'], kind, f))
    return out, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('status')
    ap.add_argument('--known', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'known.json'))
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--want', nargs='*', default=[])
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.status)))
    known = {} if a.strict else json.load(open(a.known))
    bad_known = [b for b, v in known.items() if not v.get('ref') or not v.get('fails')]
    for b in bad_known:
        print('known.json: block %s に ref / fails が無い' % b, file=sys.stderr)
    want = a.want or [r['block'] for r in rows]
    stale = [b for b in known if b not in [str(w) for w in want]]
    for b in stale:
        print('known.json: block %s は今回の対象に無い' % b, file=sys.stderr)
    out, ok = judge(rows, known, want, a.strict)
    for b, n, k, f in out:
        print('%-9s %-6s %-18s %s%s' % (k, b, n, ','.join(f) or '-', ('  ref=%s' % known[b]['ref']) if k == 'KNOWN' else ''))
    cnt = {k: sum(1 for o in out if o[2] == k) for k in ('PASS', 'KNOWN', 'NEW-FAIL', 'FIXED', 'MISSING')}
    print('judge%s: %d rows; PASS %d / KNOWN %d / NEW-FAIL %d / FIXED %d / MISSING %d' % (
        ' (strict)' if a.strict else '', len(out), cnt['PASS'], cnt['KNOWN'], cnt['NEW-FAIL'], cnt['FIXED'], cnt['MISSING']))
    sys.exit(0 if ok and not bad_known and not stale else 1)


if __name__ == '__main__':
    main()
