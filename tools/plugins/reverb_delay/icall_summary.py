#!/usr/bin/env python3
"""PLG-F4 (#201): 閉包ごとの「非 IAT 間接 call の静的件数 vs lift 後 IR」を 2 鎖分集計する (測定のみ・判定しない)。
  鎖 1 = 既定鎖 PLUG_ICALL=1 (work/batch/<block>/p.final.ll・icall/<block>.icall.json・work/batch/status.csv)
  鎖 0 = 従来鎖 PLUG_ICALL=0 (work/reverb_delay/chain0/<block>/p.final.ll・chain0/icall/<block>.icall.json・chain0/status.csv)
  列: 静的 site (機械語の非 IAT 間接 call) / IR の間接 call (callee が @name でない call; audit_icall の ir_call_ind_total) /
      dispatch 呼出 (`call void @__icall_dispatch(` の行数) / defines (`^define` 行数) / emcc -c rc (status.csv) / 入口スロットの静的件数と IR 件数
  従来鎖の IR 間接 call 0 は D1 (icall §4) の再現 (間接 call を RetDec が decoder 段で捨てる)。 既定鎖で IR 間接 call 0 でも dispatch 514 が残る。
usage: icall_summary.py <block> ...
"""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work')
M = {m['block']: p['name'] for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
     for m in p['win']['modules']}
CHAINS = [
    ('鎖 1 = 既定 PLUG_ICALL=1 (batch_lift.sh)', os.path.join(W, 'batch'), os.path.join(W, 'reverb_delay', 'icall'), os.path.join(W, 'batch', 'status.csv')),
    ('鎖 0 = 従来 PLUG_ICALL=0 (chain0_lift.sh; 測定のみ)', os.path.join(W, 'reverb_delay', 'chain0'), os.path.join(W, 'reverb_delay', 'chain0', 'icall'),
     os.path.join(W, 'reverb_delay', 'chain0', 'status.csv')),
]


def status_rows(path):
    last = {}
    for r in csv.DictReader(open(path)):
        last[int(r['block'])] = r
    return last


def table(title, ir_dir, icall_dir, status_path, blocks):
    st = status_rows(status_path)
    print('### %s' % title)
    print('| block | plugin | 非IAT 間接 call (静的 site) | うち call あり関数 | IR の間接 call (non-@name) | dispatch 呼出 | defines | emcc -c rc | 入口スロットの静的間接 call (slot=n) | 入口の IR 間接 call 合計 |')
    print('|--:|---|--:|--:|--:|--:|--:|--:|---|--:|')
    tot = [0, 0, 0, 0]
    for b in blocks:
        a = json.load(open(os.path.join(icall_dir, '%d.icall.json' % b)))
        c = json.load(open(os.path.join(W, 'closure', 'block%05d.json' % b)))
        ir = open(os.path.join(ir_dir, str(b), 'p.final.ll'), errors='replace').read()
        disp = ir.count('call void @__icall_dispatch(')
        defs = sum(1 for l in ir.split('\n') if l.startswith('define '))
        rc = st[b]['emcc_c_rc'] if b in st else 'NA'
        cmp_ = {r['fn']: r for r in a['per_fn_cmp']}
        ent, ent_ir = [], 0
        for slot, va in c['entries'].items():
            r = cmp_.get(va)
            if r and r['static_call_ind']:
                ent.append('%s=%d' % (slot, r['static_call_ind']))
                ent_ir += r['ir_call_ind']
        tot[0] += a['call_non_iat']
        tot[1] += a['ir_call_ind_total']
        tot[2] += disp
        tot[3] += defs
        print('| %d | %s | %d | %d | %d | %d | %d | %s | %s | %d |' % (
            b, M[b], a['call_non_iat'], a['fns_with_indirect_call'], a['ir_call_ind_total'], disp, defs, rc, ', '.join(ent) or '-', ent_ir))
    print('| 合計 | | %d | | %d | %d | %d | | | |' % (tot[0], tot[1], tot[2], tot[3]))
    print()


if __name__ == '__main__':
    blocks = [int(x) for x in sys.argv[1:]]
    for title, ir_dir, icall_dir, status_path in CHAINS:
        table(title, ir_dir, icall_dir, status_path, blocks)
