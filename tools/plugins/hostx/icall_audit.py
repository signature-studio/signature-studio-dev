#!/usr/bin/env python3
"""PLG-X (#210): 閉包ごとの「非 IAT 間接 call の静的件数 vs lift 後 IR の間接 call 件数」(f2/icall_summary.py と同じ定義)。
  python3 hostx/icall_audit.py <block> ...   (前提: work/batch/<block>/p.final.ll と work/closure/block<block>.ranges.txt)
各 block で tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir p.final.ll を実行し、表を stdout に出す。
exit 0 = 全 block を監査できた (静的 site があるのに IR が 0 件 = 脱落疑い、は表に出すだけで exit には影響しない)。 1 = 監査不能。
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402

W = os.path.join(P, 'work')
os.makedirs(os.path.join(W, 'hostx', 'icall'), exist_ok=True)
print('| block | 非IAT 間接 call (静的 site) | call あり関数 | IR の間接 call (audit_icall) | IR の call 行のうち callee に @ が無いもの (grep) | IR の call 行 | 閉包関数 | 判定 |')
print('|--:|--:|--:|--:|--:|--:|--:|---|')
tot = [0, 0]
rc = 0
for b in map(int, sys.argv[1:]):
    rg = os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)
    ir = os.path.join(W, 'batch', str(b), 'p.final.ll')
    fl = os.path.join(W, 'hostx', 'icall', '%d.funcs' % b)
    js = os.path.join(W, 'hostx', 'icall', '%d.icall.json' % b)
    if not (os.path.exists(rg) and os.path.exists(ir)):
        print('| %d | - | - | - | - | - | - | 監査不能 (closure/IR なし) |' % b)
        rc = 1
        continue
    with open(fl, 'w') as f:
        f.write('\n'.join(r.split('-')[0] for r in open(rg).read().replace(',', '\n').split()) + '\n')
    pe = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b)
    r = subprocess.run([sys.executable, os.path.join(P, '..', 'icall', 'audit_icall.py'), '--pe', pe, '--ir', ir,
                        '--funcs', fl, '--json', js, '--label', str(b)], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(js):
        print('| %d | - | - | - | - | - | - | audit_icall rc=%d |' % (b, r.returncode))
        rc = 1
        continue
    a = json.load(open(js))
    n_fn = sum(1 for _ in open(fl))
    calls = [l for l in open(ir) if re.match(r'\s+(%[\w.]+ = )?(tail )?call ', l)]
    no_at = sum(1 for l in calls if '@' not in l)
    tot[0] += a['call_non_iat']; tot[1] += a['ir_call_ind_total']
    verdict = '脱落 (静的>0, IR=0)' if a['call_non_iat'] and a['ir_call_ind_total'] == 0 else ('IR に残存' if a['ir_call_ind_total'] else '間接 call なし')
    print('| %d | %d | %d | %d | %d | %d | %d | %s |' % (b, a['call_non_iat'], a['fns_with_indirect_call'], a['ir_call_ind_total'], no_at, len(calls), n_fn, verdict))
print('| 合計 | %d | | %d | | | | |' % tuple(tot))
sys.exit(rc)
