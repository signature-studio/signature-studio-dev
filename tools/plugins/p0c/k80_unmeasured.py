#!/usr/bin/env python3
"""k80_unmeasured.py — #197: 80 kernel のうち差分試験 (k80_diff.py) の CSV に出ない kernel を分類する。

  python3 tools/plugins/p0c/k80_unmeasured.py [IR]   # 既定 work/diff3/k80.hb.ll (p0c4_abi_e2e.py の差分試験 IR)

判定は k80_diff.py の関数をそのまま使う (判定規則を複製しない):
  ok           = build_argmodel の leftover 0 かつ Group B でない (CSV に出る)
  groupb       = GROUP_B_HELPERS (外部 helper) を呼ぶ (数値差分対象外)
  abi-mismatch = 機械語が使い、IR 引数に割り当てられない slot がある (CSV に出ない)
  no-ir        = IR に関数が無い
出力: work/k80_unmeasured.json と、REPORT_APPENDIX_H.md に貼る表 (stdout)。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k80_diff as K  # noqa: E402


def slot_name(d):
    if isinstance(d, str):
        return d
    if isinstance(d, tuple):
        return d[0]
    return json.dumps(d, sort_keys=True)


def classify(ir, abi, labels):
    funcs = K.parse_ir_module(ir)
    rows = []
    for va in sorted(abi):
        fn = 'function_' + va[2:]
        row = {'va': va, 'labels': labels.get(va, []), 'detail': ''}
        if fn not in funcs:
            row['status'] = 'no-ir'
        else:
            F = funcs[fn]
            calls = set(re.findall(r'call [^@]*@([\w.$-]+)\(', F['body']))
            extcalls = sorted(c for c in calls if c in K.GROUP_B_HELPERS)
            mslots, irmap, status = K.build_argmodel(F, abi[va])
            assigned = {e[1] for e in irmap if e[0] == 'slot'}
            unclaimed = [slot_name(mslots[k][1]) for k, s in enumerate(mslots)
                         if s[2] and k not in assigned]
            assert (status == 'ok') == (not unclaimed), (va, status, unclaimed)
            if extcalls:
                row['status'] = 'groupb'
                row['detail'] = ','.join(x[9:] for x in extcalls)
            elif unclaimed:
                row['status'] = 'abi-mismatch'
                row['detail'] = '未割当の使用 slot: ' + ','.join(unclaimed)
            else:
                row['status'] = 'ok'
        rows.append(row)
    return rows


def main():
    ir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'diff3', 'k80.hb.ll')
    abi = json.load(open(os.path.join(HERE, 'work', 'k80abi.json')))
    cls = json.load(open(os.path.join(HERE, 'work', 'f80_classes.json')))
    labels = {r['va']: r['labels'] for r in cls['kernels']}
    rows = classify(ir, abi, labels)
    count = {}
    for r in rows:
        count[r['status']] = count.get(r['status'], 0) + 1
    print('total %d / ok %d / groupb %d / abi-mismatch %d / no-ir %d' % (
        len(rows), count.get('ok', 0), count.get('groupb', 0),
        count.get('abi-mismatch', 0), count.get('no-ir', 0)))
    out = os.path.join(HERE, 'work', 'k80_unmeasured.json')
    json.dump(rows, open(out, 'w'), indent=1, ensure_ascii=False)
    print('| kernel | 区分 | 詳細 | f80 分類 |')
    print('|---|---|---|---|')
    for r in rows:
        if r['status'] == 'ok':
            continue
        print('| %s | %s | %s | %s |' % (r['va'], r['status'], r['detail'], ','.join(r['labels'])))


if __name__ == '__main__':
    main()
