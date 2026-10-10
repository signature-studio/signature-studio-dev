#!/usr/bin/env python3
"""M11 unit #18 (function_455790 -> 44bb70 -> 446400 -> 4133f0 _UStrAsg) OOB の原因特定を liftdiff で再現する。

boot 状態 = native で InitTable の unit 0..16 を実行した直後のメモリ (ldlib.boot)。各関数を native 実機械語 vs lift wasm で差分し、
原因関数・原因類型を機械的に出力する。最後に UNIT18_SUMMARY {json} を 1 行出す。
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
from ldlib.session import Session
from ldlib import cases, irtool
import liftdiff as L

sess = Session(os.path.join(ROOT, 'targets/m11.json'), build=False, state=os.path.join(ROOT, 'work/m11/boot_state.json'))
irf = irtool.ir_features(sess.t['ir'], sess.prefix)
L.KEEP_RAW_ALL = True
L.TRACE_HEAD = 400
A = sess.lay['arena']
out = {}


def run(va, args, patch=None, blob='-', label=None):
    cases.CUSTOM['custom'] = (args.split(','), blob, patch)
    res = sess.run_functions([va], ['custom'])
    r = L.make_record(sess, res[va], irf)
    c = r['cases'][0]
    raw = c.get('raw', {})
    rec = {'fn': r['function']['name'], 'verdict': r['verdict'], 'tags': [t['tag'] for t in r.get('tags', [])],
           'outcome': c['outcome'], 'diffs': c.get('diffs', {}),
           'native_trace': raw.get('native', {}).get('trace_len'), 'wasm_trace': raw.get('wasm', {}).get('trace_len'),
           'native_status': c.get('native_status'), 'wasm_status': c.get('wasm_status')}
    if c['outcome'] in ('wasm_trap', 'both_fault'):
        rec['wasm_detail'] = (c.get('wasm_detail') or raw.get('wasm', {}).get('detail') or '')[:300]
    out[label or r['function']['name']] = rec
    return r, c


# (1) _UStrAsg: 旧値(dest が保持する文字列)の参照カウント解放。dest=arena+0x1000 は文字列 P=arena+0x3000 (refcnt@P-8 = 2) を保持
r, c = run(0x4133f0, 'i:a:0x1000,i:0x0', patch='a:0x1000:q=a:0x3000;a:0x2ff8:02000000', label='UStrAsg(dest->P[refcnt 2], src=0)')
# (2) 446370 内の経路 ( GetLocaleInfo 結果 -> UStrAsg(dest, default) )
run(0x446370, 'i:a:0x1000,i:0x0,i:0x100b,i:i:0x47dcc', label='446370(GetLocaleInfo wrapper)')
# (3) Delphi Move (409c80) — 全文字列コピーの基盤
for n in (2, 8, 20):
    run(0x409c80, 'i:a:0x1000,i:a:0x2000,i:0x%x' % n, blob='r1', label='Move(src,dst,%d)' % n)
# (4) resourcestring テーブル初期化 4123c0(table=0x455178)
run(0x4123c0, 'i:i:0x55178,i:0x0', label='4123c0(resourcestring init loop)')
# (5) 連鎖の最上位 455790 (unit #18 init): 引数なし
run(0x455790, '', label='455790 (unit #18 init)')
print('UNIT18_SUMMARY ' + json.dumps(out))
