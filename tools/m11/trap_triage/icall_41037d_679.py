#!/usr/bin/env python3
"""icall_41037d_679.py ON.json [--off OFF.json] [--expect-ok N --expect-miss M] [--top K] (#679)
  survey_units.mjs の出力 (<survey>.json と sidecar <survey>.icall.json) から, site 0x41037d (410360 の call [rbx-0x50],
  AfterConstruction; M11_OV_CLASSCREATE=1 のときだけ現れる) の unit 別内訳を出し, 次を検査する. 1 つでも外れたら exit 1.
  (1) unit 合計 ok が sidecar 累計 ok と一致 (2) 別カウンタ target 0x410070 (同じ呼出しを解決先で数えた値) の ok と一致
  (3) 最上位 unit が idx 101 (VA 0x1de960, halt0) かつ unit 合計の 99% 以上 (4) --off を渡したら OFF の 0x41037d は 0 hit
  (5) --expect-ok / --expect-miss を渡したら合計がそれに一致 (省略可)."""
import argparse, json, sys

SITE, CLS, TGT = '0x41037d', '0x41032e', '0x410070'
ap = argparse.ArgumentParser()
ap.add_argument('on'); ap.add_argument('--off'); ap.add_argument('--expect-ok', type=int); ap.add_argument('--expect-miss', type=int)
ap.add_argument('--top', type=int, default=10)
a = ap.parse_args()
bad = []

def load(path):
    per = json.load(open(path))
    side = json.load(open(path.rsplit('.json', 1)[0] + '.icall.json'))
    return per, side

per, side = load(a.on)
rows = []
for r in per:
    ic = r.get('icall', {})
    s = ic.get('sites', {}).get(SITE)
    if s and (s[0] or s[1]):
        rows.append({'unit': r['unit'], 'va': r.get('va'), 'kind': r.get('kind'), 'ok': s[0], 'miss': s[1],
                     'cls_ok': ic.get('sites', {}).get(CLS, [0, 0])[0], 'va_mb': r.get('va_mb')})
tot_ok = sum(x['ok'] for x in rows); tot_miss = sum(x['miss'] for x in rows)
tgt_ok = sum(r.get('icall', {}).get('targets', {}).get(TGT, [0, 0])[0] for r in per)
side_ok, side_miss = side['total']['sites'].get(SITE, [0, 0])
print('site %s (ON %s): unit 合計 ok=%d miss=%d, 当たった unit %d 本 (survey %d unit)' % (SITE, a.on, tot_ok, tot_miss, len(rows), len(per)))
print('  sidecar 累計 ok=%d miss=%d / target %s の unit 合計 ok=%d' % (side_ok, side_miss, TGT, tgt_ok))
print('  %-4s %-9s %-8s %-7s %12s %8s %12s %s' % ('unit', 'va', 'kind', 'va_mb', 'ok', 'miss', 'ok(%s)' % CLS, 'share'))
rows.sort(key=lambda x: -x['ok'])
for x in rows[:a.top]:
    print('  %-4d %-9s %-8s %-7s %12d %8d %12d %6.3f%%' % (x['unit'], x['va'], x['kind'], x['va_mb'], x['ok'], x['miss'], x['cls_ok'], 100.0 * x['ok'] / tot_ok))
rest = tot_ok - (rows[0]['ok'] if rows else 0)
print('  上位 1 unit 以外の合計 ok=%d (%d unit)' % (rest, len(rows) - 1))

if tot_ok != side_ok or tot_miss != side_miss: bad.append('(1) unit 合計 != sidecar 累計')
if tot_ok != tgt_ok: bad.append('(2) site ok %d != target %s ok %d' % (tot_ok, TGT, tgt_ok))
if not rows or rows[0]['unit'] != 101 or rows[0]['va'] != '0x1de960' or rows[0]['kind'] != 'halt0' or rows[0]['ok'] < 0.99 * tot_ok:
    bad.append('(3) 最上位 unit が idx 101 (0x1de960 halt0) かつ 99%% 以上でない: %s' % (rows[0] if rows else None))
if a.off:
    off = json.load(open(a.off))
    hit = sum(sum(r.get('icall', {}).get('sites', {}).get(SITE, [0, 0])) for r in off)
    print('OFF %s: site %s の hit 合計 = %d' % (a.off, SITE, hit))
    if hit: bad.append('(4) OFF なのに %s が %d hit' % (SITE, hit))
if a.expect_ok is not None and tot_ok != a.expect_ok: bad.append('(5) ok %d != 期待 %d' % (tot_ok, a.expect_ok))
if a.expect_miss is not None and tot_miss != a.expect_miss: bad.append('(5) miss %d != 期待 %d' % (tot_miss, a.expect_miss))
for b in bad: print('FAIL', b)
print('RESULT', 'FAIL' if bad else 'PASS')
sys.exit(1 if bad else 0)
