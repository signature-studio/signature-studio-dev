#!/usr/bin/env python3
"""InitUnits (System.@InitUnits, image 0x4120c0) の空振り一致を検出する (LD-25 / #977)。

InitUnits は InitTable (RVA 0x11eac90 の参照先) と InitCount (0x11eac98) を読み、
それが空なら何もせず戻る。boot 状態にこれが無いと、native / wasm とも何もせず ok となり、
比較情報ゼロの「一致」が出る (空振り一致)。

  units  : work/m11/boot_state.json (batch 既定。liftdiff_e2e.sh [3/4] が作る)
  hybrid : 本スクリプトが work/m11/boot_state_hybrid.json を作る (InitTable を充足)

判定: 両 state で InitUnits の 11 pattern を実行し、
  - EMPTY = equal かつ 呼出列・書込みが両側 0 件 (比較情報なし)
  - hybrid で EMPTY が 1 件でもあれば FAIL (exit 1)
  - hybrid で native_status が ok でない (segv 等) が 1 件でもあれば FAIL (exit 1) (LD-153)
units の EMPTY 件数は空振りの実測として出力する (defect の記録であり FAIL 条件ではない)。

使い方: FL_WIN64_DIR=... python3 tests/check_initunits.py [--json out.json]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ldlib.session import Session
from ldlib import boot, cases

TARGET = 'targets/m11.json'
INITUNITS_VA = 0x4120c0
UNITS_STATE = os.path.join(ROOT, 'work/m11/boot_state.json')
HYBRID_STATE = os.path.join(ROOT, 'work/m11/boot_state_hybrid.json')


def make_hybrid_state():
    sess = Session(TARGET, shards=1, build=False, trace=True)
    r, res = boot.build_state(sess, None, mode='hybrid')
    json.dump(res, open(HYBRID_STATE, 'w'))
    st = res['state']
    print('[boot] hybrid units_run=%s/%s first_fail=%s heap_used=%s -> %s' % (
        res['units_run'], res['units_total'], res['first_fail'], st['heap_used'], HYBRID_STATE))


def observe(c):
    n, w = c['_n'], c['_w']
    ncalls = len(n.get('calls') or [])
    wcalls = len(w.get('calls') or [])
    nmem = len(n.get('mem') or [])
    wmem = len(w.get('mem') or [])
    return {
        'pattern': c['pattern'],
        'outcome': c['outcome'],
        'native_status': c.get('native_status'),
        'wasm_status': c.get('wasm_status'),
        'native_calls': ncalls, 'wasm_calls': wcalls,
        'native_mem': nmem, 'wasm_mem': wmem,
        'empty': c['outcome'] == 'equal' and ncalls == 0 and wcalls == 0 and nmem == 0 and wmem == 0,
    }


def run_state(path):
    sess = Session(TARGET, shards=1, build=False, trace=True, state=path)
    if not sess.sigs.get(sess.fn_name(INITUNITS_VA), {}).get('defined'):
        raise SystemExit('InitUnits が wasm 定義に無い')
    nat, was = sess.make_runners()
    try:
        rec = sess._run_one(nat, was, INITUNITS_VA, cases.PATTERN_NAMES, with_refine=False)
    finally:
        nat.close(); was.close()
    return [observe(c) for c in rec['cases']]


def main():
    out = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else None
    if not os.path.exists(UNITS_STATE):
        raise SystemExit('missing %s (先に liftdiff.py bootstate を実行)' % UNITS_STATE)
    make_hybrid_state()
    summary = {'va': hex(INITUNITS_VA)}
    fail = False
    for mode, path in (('units', UNITS_STATE), ('hybrid', HYBRID_STATE)):
        st = json.load(open(path))['state']
        pc = boot.precondition(st)
        rows = run_state(path)
        empty = sum(1 for r in rows if r['empty'])
        native_ng = sum(1 for r in rows if r['native_status'] != 'ok')
        summary[mode] = {
            'precondition': pc,
            'patterns': len(rows),
            'outcomes': {o: sum(1 for r in rows if r['outcome'] == o) for o in {r['outcome'] for r in rows}},
            'empty_match': empty,
            'native_not_ok': native_ng,
            'rows': rows,
        }
        print('[%s] precondition=%s patterns=%d empty_match=%d native_not_ok=%d outcomes=%s' % (mode, pc, len(rows), empty, native_ng, summary[mode]['outcomes']))
        for r in rows:
            print('  %-7s %-12s native=%s wasm=%s calls=%d/%d mem=%d/%d%s' % (
                r['pattern'], r['outcome'], r['native_status'], r['wasm_status'],
                r['native_calls'], r['wasm_calls'], r['native_mem'], r['wasm_mem'],
                '  [EMPTY]' if r['empty'] else ''))
        if mode == 'hybrid' and (empty or native_ng):
            fail = True
    if out:
        json.dump(summary, open(out, 'w'), ensure_ascii=False, indent=1)
    print('CHECK_INITUNITS %s' % ('FAIL' if fail else 'PASS'))
    if fail:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
