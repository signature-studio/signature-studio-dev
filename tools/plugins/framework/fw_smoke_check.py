#!/usr/bin/env python3
"""fw_smoke_check.py — framework smoke の合否を独立に再計算する (CAB-269, 規則 36・37).

`fw_run.mjs` の stderr 出力 (`[fw] SMOKE PASS ...: dispatch=%d units_done=%d va=%d heap=%d ff=%d`)
を **別正規表現で** パースし、CAB-269 受入条件の期待値と照合する。fw_run.mjs の集計ロジックは
使わない (同実装の再実行は独立再計算ではない)。

  python3 fw_smoke_check.py [--log smoke.log] [--wasm fw_route.wasm]
                            [--expect dispatch=38 units_done=0 va=1 heap=1 ff=0]
                            [--size 14828623]

数え方の定義 (規則 36):
  * dispatch = `fw_dispatch_count()` (BLK 経由の間接 call 延べ件数・trace 行数ではない)
  * units_done = 0x714C98 の u32 (InitUnits が完了した unit 数)
  * va / heap = `fw_va_calls()` / `fw_alloc_count()` (varargs 呼出件数 / 確保件数)
  * ff = `fw_ff_count()` (fail-fast 到達件数・0 が正常)
  * wasm size = `fw_route.wasm` の実ファイルバイト数 (fw_route.cjs の JS 部分ではない)
"""
import argparse
import os
import re
import sys

PASS_RE = re.compile(
    r'^\[fw\] SMOKE PASS \([^)]*\): dispatch=(\d+) units_done=(-?\d+) va=(\d+) heap=(\d+) ff=(\d+)')
FAIL_RE = re.compile(r'^\[fw\] SMOKE FAIL: (.*)$')
DEF_EXPECT = {'dispatch': 38, 'units_done': 0, 'va': 1, 'heap': 1, 'ff': 0}
DEF_SIZE = 14828623      # CAB-194 再ビルド (vfy194/fw_route_194_rebuild.wasm) の実測バイト数


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default='smoke.log')
    ap.add_argument('--wasm', default='fw_route.wasm')
    ap.add_argument('--expect', nargs='*', default=[])
    ap.add_argument('--size', type=int, default=DEF_SIZE)
    a = ap.parse_args(argv)

    expect = dict(DEF_EXPECT)
    for kv in a.expect:
        k, v = kv.split('=')
        expect[k] = int(v)

    txt = open(a.log, errors='replace').read()
    lines = [l.strip() for l in txt.split('\n') if l.strip()]
    got = None
    fail = None
    for l in lines:
        m = PASS_RE.match(l)
        if m:
            got = {'dispatch': int(m.group(1)), 'units_done': int(m.group(2)),
                   'va': int(m.group(3)), 'heap': int(m.group(4)), 'ff': int(m.group(5))}
            break
        m = FAIL_RE.match(l)
        if m:
            fail = m.group(1)
    if got is None:
        print('[fw_smoke_check] FAIL: PASS 行が無い (FAIL 行: %s)' % (fail or 'なし'))
        return 1

    rows = []
    ok = True
    for k in ('dispatch', 'units_done', 'va', 'heap', 'ff'):
        same = got[k] == expect[k]
        ok = ok and same
        rows.append('  %-11s got=%-6d expect=%-6d %s' % (k, got[k], expect[k], 'OK' if same else '** MISMATCH **'))
    if os.path.exists(a.wasm):
        size = os.path.getsize(a.wasm)
        same = size == a.size
        ok = ok and same
        rows.append('  %-11s got=%-6d expect=%-6d %s' % ('wasm_B', size, a.size, 'OK' if same else '** MISMATCH **'))
    else:
        rows.append('  %-11s (ファイル無し: %s)' % ('wasm_B', a.wasm))
    print('[fw_smoke_check] ' + ('PASS' if ok else 'FAIL'))
    print('\n'.join(rows))
    print('  source: %s (%d 行)' % (a.log, len(lines)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
