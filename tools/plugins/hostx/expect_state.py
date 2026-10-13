#!/usr/bin/env python3
"""既知不合格の block が「期待どおりの不合格」のままであることを固定する (合格に変わったら exit 1 = 方針表の更新が必要)。
  python3 hostx/expect_state.py <status.csv> <block> ... [-o out.csv]
期待: 24161 (ReWired) = emcc_c_rc != 0 かつ f80_funcs > 0 / 19304 (ZGE 殻) = lift_rc または emcc_c_rc のどちらかが 0 以外、
      または 閉包関数数が 1000 を超える (T3 規模)。 ZGE 殻が合格した場合は方針表の「殻は lift 可」へ更新が要る。
exit: 0 = 期待どおり / 1 = 期待と異なる (合格に変わった等) / 2 = 入力不正
"""
import argparse, csv, sys

ap = argparse.ArgumentParser()
ap.add_argument('status_csv')
ap.add_argument('blocks', nargs='+')
ap.add_argument('-o', '--out')
a = ap.parse_args()
try:
    rows = list(csv.reader(open(a.status_csv, newline='')))
except OSError as e:
    print('expect_state: cannot read:', e, file=sys.stderr); sys.exit(2)
hdr = rows[0]
ix = {c: hdr.index(c) for c in hdr}
last = {r[ix['block']]: r for r in rows[1:] if len(r) == len(hdr)}
bad, body = 0, []
for b in a.blocks:
    r = last.get(b)
    if r is None:
        print('expect_state: no row for', b); sys.exit(2)
    body.append(r)
    v = {c: int(r[ix[c]]) for c in ('closure_funcs', 'lift_rc', 'f80_funcs', 'emcc_c_rc', 'declares_unimpl')}
    if b == '24161':
        ok = v['emcc_c_rc'] != 0 and v['f80_funcs'] > 0
    elif b == '19304':
        ok = v['lift_rc'] != 0 or v['emcc_c_rc'] != 0 or v['closure_funcs'] > 1000
    else:
        ok = True
    bad += not ok
    print('expect_state: %s %s closure_funcs=%d lift_rc=%d f80=%d unimpl=%d emcc_c=%d -> %s' % (
        b, r[ix['name']], v['closure_funcs'], v['lift_rc'], v['f80_funcs'], v['declares_unimpl'], v['emcc_c_rc'],
        '期待どおり (不合格のまま)' if ok else '期待と異なる (方針表の更新が必要)'))
if a.out:
    csv.writer(open(a.out, 'w', newline='')).writerows([hdr] + body)
sys.exit(1 if bad else 0)
