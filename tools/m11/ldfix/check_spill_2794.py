#!/usr/bin/env python3
"""check_spill_2794.py — spill 宛 TRUE_DROP 修復 (#2794) の検収。修復前後の audit と fix_spill_2794.py の報告を突合する。

検査 (1 つでも外れたら exit 1):
  C1 修復後の spill 宛 CELL_COLLAPSED 集合 ⊆ 修復前の集合 (修復で新たに CELL_COLLAPSED が増えてはならない)
  C2 修復前 − 修復後 = 1 対 1 の修復集合 (消えた site と 1 対 1 で修復した site が一致する)
  C2b callarg 根拠の修復 (#2910) は修復後も audit に残る (関数 × K 判定) ことを確かめる
  C3 修復した site はすべて TRUE_DROP (判定 TSV)
出力: 判定 TRUE_DROP の 24 site 全件の表 (fn・site・status・理由) を OUT.tsv に書く。
使い方: python3 check_spill_2794.py BEFORE.json AFTER.json REPORT.json SPILL37.tsv OUT.tsv
"""
import json
import sys


def frame_collapsed(audit):
    out = set()
    for va, v in audit['functions'].items():
        for s in v['sites']:
            c = s.get('cell')
            if s.get('frame') and c and c.get('verdict') == 'CELL_COLLAPSED':
                out.add((va, s['addr']))
    return out


def main():
    before = frame_collapsed(json.load(open(sys.argv[1])))
    after = frame_collapsed(json.load(open(sys.argv[2])))
    rep = json.load(open(sys.argv[3]))
    rows = [l.rstrip('\n').split('\t') for l in open(sys.argv[4])][1:]
    out_path = sys.argv[5]
    fixed = {(x['fn'], x['site']): x for x in rep['fixed']}
    skipped = {(x['fn'], x['site']): x for x in rep['skipped']}
    verdict = {(r[0], r[1]): r[3] for r in rows if len(r) > 3}
    removed = before - after
    fixed_set = set(fixed)
    # callarg 根拠 (#2910) の修復は、audit が関数 × K 単位で判定するため、同じ K の別の i32 読み出しが残る限り CELL_COLLAPSED のまま残る。
    # ただし icmp 側の根拠 (#4418) で同じ (関数, K) の i32 読み出しを全て直した場合は、その (関数, K) の callarg site も audit から消える。
    cmp_groups = {(x['fn'], x['K']) for x in rep.get('cmp_fixed', [])}
    callarg = {k for k in fixed_set if fixed[k].get('ev', '1to1') != '1to1'}
    callarg_open = {k for k in callarg if (k[0], fixed[k]['K']) not in cmp_groups}
    callarg_cleared = callarg - callarg_open
    ok = True
    if not after <= before:
        print('FAIL C1: 修復後に新たな spill 宛 CELL_COLLAPSED が出た: %s' % sorted(after - before)[:5])
        ok = False
    if removed != (fixed_set - callarg) | callarg_cleared:
        print('FAIL C2: 消えた site %d 件 != 1 対 1 + icmp 根拠で消える callarg の %d 件 (差 %s)' % (len(removed), len((fixed_set - callarg) | callarg_cleared), sorted(removed ^ ((fixed_set - callarg) | callarg_cleared))[:5]))
        ok = False
    if callarg_open - after:
        print('FAIL C2b: callarg 根拠の修復 site が audit から消えた (判定の粒度の前提が崩れた): %s' % sorted(callarg_open - after)[:5])
        ok = False
    print('callarg 根拠の修復 %d site は audit 上 CELL_COLLAPSED のまま (同一 K の別読み出しが残る)' % len(callarg_open & after))
    print('callarg 根拠の修復 %d site は icmp 根拠 (cmp) の修復で同じ (関数, K) が全て直り audit から消えた' % len(callarg_cleared))
    bad = [k for k in fixed_set if verdict.get(k) != 'TRUE_DROP']
    if bad:
        print('FAIL C3: TRUE_DROP 以外を修復した: %s' % bad)
        ok = False
    print('spill 宛 CELL_COLLAPSED: 修復前 %d site -> 修復後 %d site (消えた %d、修復 %d)' % (len(before), len(after), len(removed), len(fixed_set)))
    lines = ['fn\tsite\tverdict\tK\tstatus\twhy\tmachine_refs\tir_refs']
    for r in rows:
        if len(r) < 4 or r[3] != 'TRUE_DROP':
            continue
        k = (r[0], r[1])
        if k in fixed:
            x, st, why = fixed[k], 'REPAIRED', fixed[k].get('ev', '1to1')
        else:
            x = skipped.get(k, dict(K='-', m='-', i='-', why='not_candidate'))
            st, why = 'SKIPPED', x['why']
        lines.append('%s\t%s\tTRUE_DROP\t%s\t%s\t%s\t%s\t%s' % (r[0], r[1], x['K'], st, why, x['m'], x['i']))
    open(out_path, 'w').write('\n'.join(lines) + '\n')
    print('TRUE_DROP %d site: REPAIRED %d / SKIPPED %d' % (len(lines) - 1, len(fixed_set), len(lines) - 1 - len(fixed_set)))
    print('RESULT: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
