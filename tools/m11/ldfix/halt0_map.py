#!/usr/bin/env python3
"""halt0_map.py — survey (shimx survey_trace) の per-unit JSON から
halt0 unit の `Runtime error 0 at 0x…` 発生点 (MessageBoxA text) を抽出し,
発生アドレス (LVA) → 関数 (VA/.pdata) → unit の対応表を作る (CAB-129 REPORT §5 の継続, CAB-131)。

使い方: python3 halt0_map.py SURVEY1.json [SURVEY2.json ...] [--out OUT.json]
  survey JSON 形式: {summary:{kinds:{...}}, per_unit:[{unit,lva,kind,detail,shim_calls,msgs?}]}
"""
import argparse
import bisect
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MSG_RE = re.compile(r"Runtime error\s+(\d+) at ([0-9A-Fa-f]+)")


def load_fn_table(pe_path):
    """VA → 関数名 (.pdata 区間の先頭関数) の境界表"""
    from ldmach import Machine
    m = Machine(pe_path)
    vas = sorted(m.fns.keys())
    return m, vas


def fn_at(m, vas, va):
    k = bisect.bisect_right(vas, va) - 1
    if k < 0:
        return None
    fva = vas[k]
    beg, size = m.fns[fva]
    if not (fva <= va < fva + size):
        return None
    return 'function_%x' % fva


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('surveys', nargs='+')
    ap.add_argument('--pe', default='/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin')
    ap.add_argument('--out')
    a = ap.parse_args()
    m, vas = load_fn_table(a.pe)
    agg = {}
    for path in a.surveys:
        d = json.load(open(path))
        name = d.get('summary', {}).get('variant') or os.path.basename(path)
        for u in d.get('per_unit', []):
            if u.get('kind') != 'halt0':
                continue
            for msg in (u.get('msgs') or []):
                mm = MSG_RE.search(msg)
                if not mm:
                    continue
                err, addr = int(mm.group(1)), int(mm.group(2), 16)
                va = addr + 0x400000
                fn = fn_at(m, vas, va)
                key = (name, addr, err)
                e = agg.setdefault(key, {'units': [], 'fn': fn})
                e['units'].append(u.get('unit'))
    rows = []
    for (name, addr, err), e in sorted(agg.items(), key=lambda kv: (-len(kv[1]['units']), kv[0][1])):
        rows.append({'survey': name, 'err': err, 'lva': '0x%X' % addr,
                     'va': '0x%X' % (addr + 0x400000), 'fn': e['fn'],
                     'n_units': len(e['units']), 'units': sorted(e['units'])})
    for r in rows:
        print('%-28s err=%d at %s (%s) n=%d units=%s' % (
            r['survey'], r['err'], r['lva'], r['fn'] or '?', r['n_units'],
            ','.join(map(str, r['units'][:24])) + ('...' if r['n_units'] > 24 else '')))
    if a.out:
        json.dump(rows, open(a.out, 'w'), indent=1, ensure_ascii=False)
        print('[halt0_map] wrote %s (%d rows)' % (a.out, len(rows)))


if __name__ == '__main__':
    main()
