#!/usr/bin/env python3
"""PLG-F2 (#199): 閉包ごとの「非 IAT 間接 call の静的件数 vs lift 後 IR の間接 call 件数」を集計する。
入力: work/f2/<block>.icall.json (tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir work/batch/<block>/p.final.ll)
      work/closure/block<block>.json (入口スロット)
出力: markdown 表 (stdout)。 Eff_Render / ProcessParam など入口スロットごとの静的間接 call 件数と IR 件数も出す。
  python3 tools/plugins/f2/icall_summary.py <block> ...
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work')
M = {m['block']: p['name'] for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
     for m in p['win']['modules']}
S = {r['block']: r for r in json.load(open(os.path.join(W, 'f2_stats.json')))}
print('| block | plugin | 非IAT 間接 call (静的 site) | うち call あり関数 | IR の間接 call | 入口スロットの静的間接 call (slot=n) | 入口の IR 間接 call 合計 | IR leaf / うち機械語でも間接 call 無し |')
print('|--:|---|--:|--:|--:|---|--:|--:|')
tot = [0, 0, 0, 0]
for b in map(int, sys.argv[1:]):
    a = json.load(open(os.path.join(W, 'f2', '%d.icall.json' % b)))
    c = json.load(open(os.path.join(W, 'closure', 'block%05d.json' % b)))
    cmp_ = {r['fn']: r for r in a['per_fn_cmp']}
    ent = []
    ent_ir = 0
    for slot, va in c['entries'].items():
        r = cmp_.get(va)
        if r and r['static_call_ind']:
            ent.append('%s=%d' % (slot, r['static_call_ind']))
            ent_ir += r['ir_call_ind']
    with_ind = {r['fn'] for r in a['per_fn_cmp'] if r['static_call_ind']}
    leaf = [l['fn'][len('function_'):] for l in S[b]['leaf_funcs']]
    true_leaf = [f for f in leaf if '0x' + f not in with_ind]
    tot[0] += a['call_non_iat']
    tot[1] += a['ir_call_ind_total']
    tot[2] += len(leaf)
    tot[3] += len(true_leaf)
    print('| %d | %s | %d | %d | %d | %s | %d | %d / %d |' % (b, M[b], a['call_non_iat'], a['fns_with_indirect_call'],
                                                          a['ir_call_ind_total'], ', '.join(ent) or '-', ent_ir,
                                                          len(leaf), len(true_leaf)))
print('| 合計 | | %d | | %d | | | %d / %d |' % tuple(tot))
