#!/usr/bin/env python3
"""#5406 (LD-268): fvm case 42 件の阻害要因を分類する (集計のみ・実行はしない)。
使い方: python3 tools/liftdiff/ld5406_fvm_classify.py [batch jsonl]  (既定 work/m11/batch_sample_800.jsonl)
入力: liftdiff_e2e.sh --m11-only の batch jsonl (fvm case を含む)。出力: 分類ごとの件数と関数 VA 一覧。
分類 (排他):
  native_null_field : native が fault addr 0x0〜0xff (this 由来の NULL フィールド参照。this の VMT blob に値が無い)
  native_noaddr     : native fault に addr が無い (rip の不正遷移・ret 等)
  native_other_addr : native fault addr が this (0x1000) 系でも候補引数 SMALL[i]+FVM_OFF 内でもない
  native_cand_arg   : native fault addr が候補引数 SMALL[i] + off (FVM_OFF 未満) の範囲
  wasm_stub_unreach : both_fault で wasm が unreachable (4128b0 系の未解決 call スタブ)
  wasm_oob          : both_fault で wasm が memory access out of bounds
  wasm_other        : both_fault で wasm がその他の trap
  diff              : 両方 ok で比較して差分あり (既知の wasm 欠陥 or native_extra_call)
"""
import json
import os
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldlib import cases  # noqa: E402


def classify(c, arg):
    if c['outcome'] == 'diff':
        return 'diff'
    if c['outcome'] == 'native_fault':
        base = 'native'
    elif c['outcome'] == 'both_fault':
        det = c.get('wasm_detail', '')
        if 'unreachable' in det:
            return 'wasm_stub_unreach'
        if 'out of bounds' in det:
            return 'wasm_oob'
        return 'wasm_other'
    else:
        return 'other:' + c['outcome']
    f = c.get('fault') or {}
    if 'addr' not in f:
        return 'native_noaddr'
    a = int(f['addr'], 16)
    if arg is not None and arg < len(cases.SMALL) and 0 <= a - cases.SMALL[arg] < cases.FVM_OFF:
        return 'native_cand_arg'
    if a < 0x100:
        return 'native_null_field'
    return 'native_other_addr'


def main(path):
    cnt = collections.Counter()
    members = collections.defaultdict(list)
    fns = 0
    for line in open(path):
        r = json.loads(line)
        cs = [c for c in r['cases'] if c.get('pattern') == 'fvm']
        if not cs:
            continue
        fns += 1
        for c in cs:
            k = classify(c, c.get('fvm_arg'))
            cnt[k] += 1
            members[k].append(r['function']['va'])
    print('fvm functions', fns, 'fvm cases', sum(cnt.values()))
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print('%-20s %3d  %s' % (k, v, ' '.join(members[k])))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'm11', 'batch_sample_800.jsonl'))
