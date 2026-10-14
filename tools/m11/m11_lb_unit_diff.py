#!/usr/bin/env python3
# M11 LB 依存差の unit 別突合 (#3188): 2 本の寛容起動記録 (m11_tolerant.mjs の M11_TOLERANT_OUT) を index で比べ、結果 (kind) が違う unit を出す。
#   使い方: python3 tools/m11/m11_lb_unit_diff.py <LB=0 の tolerant_units.json> <LB=0x10000 の tolerant_units.json>
#   units の要素は [i, va, kind, va_bytes, getmem, freemem, oom, clobber]。VA は LB ぶんずれるので比較に使わず、index と kind だけで比べる。
#   出力: 差の件数・各 unit の kind (左 / 右)・skipped の msg (左 / 右)。差が 0 件なら exit 0、1 件以上なら exit 1。
import json
import sys


def load(p):
    with open(p, encoding='utf-8') as f:
        d = json.load(f)
    units = {u[0]: u for u in d['units']}
    skipped = {s['i']: s for s in d['skipped']}
    return units, skipped


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip())
        return 2
    la, sa = load(sys.argv[1])
    lb, sb = load(sys.argv[2])
    idx = sorted(set(la) | set(lb))
    diffs = []
    for i in idx:
        ua, ub = la.get(i), lb.get(i)
        ka = ua[2] if ua else None
        kb = ub[2] if ub else None
        if ka != kb:
            diffs.append((i, ua[1] if ua else None, ka, kb,
                          sa.get(i, {}).get('msg'), sb.get(i, {}).get('msg')))
    print('units: left=%d right=%d common=%d' % (len(la), len(lb), len(set(la) & set(lb))))
    print('skipped: left=%d right=%d' % (len(sa), len(sb)))
    print('kind_diff=%d' % len(diffs))
    for i, va, ka, kb, ma, mb in diffs:
        print('unit %d va=%s left=%s right=%s' % (i, va, ka, kb))
        if ma or mb:
            print('  msg left=%s' % (ma,))
            print('  msg right=%s' % (mb,))
    return 0 if not diffs else 1


if __name__ == '__main__':
    sys.exit(main())
