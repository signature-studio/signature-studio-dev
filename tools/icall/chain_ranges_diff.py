#!/usr/bin/env python3
"""chain_ranges_diff.py — Fresh Air の関数範囲で chained=True/False を比べ、CHAININFO 断片による伸長件数を出す (#1838)。
  python3 tools/icall/chain_ranges_diff.py <SlateCore.core_64> <clo_freshair_all.json>
出力: 範囲の総数・伸長件数・伸長した VA と範囲・伸長後の範囲が他関数の開始 VA を含むか (含めば FAIL)。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_icall as A
import prep_targets as P


def main(pe_path, json_path):
    fa = json.load(open(json_path))
    vas = sorted({int(f['va'], 16) for f in fa['funcs']})
    img = A.Image(pe_path)
    off = P.ranges_with_ends(img, vas, chained=False)
    on = P.ranges_with_ends(img, vas, chained=True)
    assert len(off) == len(on), 'chained の有無で行数が変わった'
    print('entries', len(on), 'chained=False vs True 差分 (行)', sum(1 for a, b in zip(off, on) if a != b))
    par = P.chain_parents(img)
    fails = 0
    for a, b in zip(off, on):
        if a == b:
            continue
        va = int(a.split('-')[0], 16)
        s, e = (int(x, 16) for x in b.split('-'))
        own = {x for x, p in par.items() if p == va}
        leak = [hex(x) for x in img.pdata_starts if s < x < e and x not in own]
        print(a, '->', b, 'leak', leak or 'none')
        fails += bool(leak)
    print('FAIL' if fails else 'PASS', 'leak 件数', fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
