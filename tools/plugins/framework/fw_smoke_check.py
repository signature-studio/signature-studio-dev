#!/usr/bin/env python3
"""fw_smoke_check.py — framework smoke の合否を独立に再計算する (CAB-269, 規則 36・37).

`fw_run.mjs` の stderr 出力 (`[fw] SMOKE PASS ...: dispatch=%d units_done=%d va=%d heap=%d ff=%d`)
を **別正規表現で** パースし、期待値と照合する。fw_run.mjs の集計ロジックは
使わない (同実装の再実行は独立再計算ではない)。

  python3 fw_smoke_check.py [--log smoke.log] [--wasm fw_route.wasm] [--image fw_image.bin]
                            [--expect runerr=0 ff=0 init_reach=288]
                            [--size 14828623]

判定基準 (#2425 で再定義。旧 `dispatch=38` は InitUnits 完走の証拠にならないため外した):
  * runerr = `[fw][MessageBoxA] Error: Runtime [error ]N at ADDR` (RunError) の件数。0 が正常
  * ff = `fw_ff_count()` (fail-fast 到達件数・0 が正常)
  * init_reach = InitTable (fw_image.bin の VA 0x6c1460・16 byte/entry・先頭が Init) の Init 値のうち、
    最初の RunError より前に `[dispatch]` の target として現れた最大 unit idx。
    間接呼出 (`__icall_dispatch`) だけが記録されるため **下限**。完走の目標は Init 非 0 の最後の idx (288)。
  * 情報のみ (ゲートしない): dispatch / units_done / va / heap。数え方の定義 (規則 36):
    - dispatch = `fw_dispatch_count()` (BLK 経由の間接 call 延べ件数・trace 行数ではない)
    - units_done = 0x714C98 の u32 (InitUnits が完了した unit 数の意図。stage-2 では 0 のまま)
    - va / heap = `fw_va_calls()` / `fw_alloc_count()` (varargs 呼出件数 / 確保件数)
  * wasm size = `fw_route.wasm` の実ファイルバイト数 (fw_route.cjs の JS 部分ではない)
"""
import argparse
import os
import re
import struct
import sys

PASS_RE = re.compile(
    r'^\[fw\] SMOKE PASS \([^)]*\): dispatch=(\d+) units_done=(-?\d+) va=(\d+) heap=(\d+) ff=(\d+)')
FAIL_RE = re.compile(r'^\[fw\] SMOKE FAIL: (.*)$')
RUNERR_RE = re.compile(r'^\[fw\]\[MessageBoxA\] Error: Runtime (?:error )?(\d+) at ([0-9a-fA-F]+)')
DISPATCH_RE = re.compile(r'^\[dispatch\] site=0x[0-9a-fA-F]+ -> target=(0x[0-9a-fA-F]+)')
DEF_EXPECT = {'runerr': 0, 'ff': 0, 'init_reach': 288}
INFO_KEYS = ('dispatch', 'units_done', 'va', 'heap')
IMG_BASE = 0x400000          # fw_image.bin の先頭 = VA 0x400000
TAB_VA = 0x6c1460            # InitTable (fw_table.py)
TAB_N = 0x122                # 290 unit (idx 289 は Init 0)
DEF_SIZE = 0                 # 0 = wasm サイズを照合しない (既定)。参照値: 14,828,623 B (77cde78 vintage) / 15,061,227 B (HEAD)


def init_table(img_path):
    img = open(img_path, 'rb').read()
    return [struct.unpack_from('<Q', img, TAB_VA - IMG_BASE + 16 * i)[0] for i in range(TAB_N)]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default='smoke.log')
    ap.add_argument('--wasm', default='fw_route.wasm')
    ap.add_argument('--image', default='fw_image.bin')
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

    rr = [i for i, l in enumerate(lines) if RUNERR_RE.match(l)]
    got['runerr'] = len(rr)
    cut = rr[0] if rr else len(lines)
    seen = set()
    for l in lines[:cut]:
        m = DISPATCH_RE.match(l)
        if m:
            seen.add(int(m.group(1), 16))
    tab = init_table(a.image) if os.path.exists(a.image) else []
    reached = [i for i, va in enumerate(tab) if va and va in seen]
    got['init_reach'] = max(reached) if reached else -1

    rows = []
    ok = True
    for k in ('runerr', 'ff', 'init_reach'):
        same = got[k] == expect[k]
        ok = ok and same
        rows.append('  %-11s got=%-6d expect=%-6d %s' % (k, got[k], expect[k], 'OK' if same else '** MISMATCH **'))
    for k in INFO_KEYS:
        rows.append('  %-11s got=%-6d (情報・非ゲート)' % (k, got[k]))
    if a.size and os.path.exists(a.wasm):
        size = os.path.getsize(a.wasm)
        same = size == a.size
        ok = ok and same
        rows.append('  %-11s got=%-6d expect=%-6d %s' % ('wasm_B', size, a.size, 'OK' if same else '** MISMATCH **'))
    else:
        rows.append('  %-11s (照合スキップ: --size 未指定・実測 %s)' % ('wasm_B', os.path.getsize(a.wasm) if os.path.exists(a.wasm) else 'n/a'))
    print('[fw_smoke_check] ' + ('PASS' if ok else 'FAIL'))
    print('\n'.join(rows))
    print('  source: %s (%d 行)' % (a.log, len(lines)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
