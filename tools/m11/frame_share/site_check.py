#!/usr/bin/env python3
"""site_check.py: 親の mov rcx,rbp 渡し site ごとに、call 直前の引数 (rdx 等) と callee の読み先を機械語で並べる (#4189 / SHX-T44)。

使い方:
  FL_WIN64_DIR=<展開先> python3 frame_share/site_check.py [--parent 448490] [--pe PE]
  FL_WIN64_DIR=<展開先> python3 frame_share/site_check.py --sites work/frame_share.json --out work/site_check.json
出力: site ごとの call VA・callee・call 直前 6 命令・callee の rbp 基準アクセス (off:size:kind)。
--sites 指定時は detect.py の mov・shared site 全件 (301) を JSON に書く (rdx の種別・callee 読み先の最大端・親 IR の alloca との突合は base_check.py)。
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import detect  # noqa: E402


def site_record(mach, cs, pins, i, got, ins, parent):
    cva = ins.operands[0].imm
    cins = mach.disasm_fn(cva)
    hits = detect.walk_callee(cs, cins, got[0]) if cins else []
    acc = sorted(set((h['off'], h['size'], h['kind']) for h in hits))
    before = [j.mnemonic + ' ' + j.op_str for j in pins[max(0, i - 6):i + 1]]
    return dict(parent=parent, call_at='0x%x' % ins.address, callee='function_%x' % cva,
                pre_call=before, callee_access=[dict(off=o, size=s, kind=k) for (o, s, k) in acc])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parent', default='448490')
    ap.add_argument('--sites', help='detect.py の出力 JSON。mov・shared の全 site を処理する')
    ap.add_argument('--out')
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    a = ap.parse_args()
    mach = Machine(a.pe)
    cs = mach.cs
    if a.sites:
        data = json.load(open(a.sites))
        mov = [s for s in data['sites'] if s['how'] == 'mov' and s['cls'] == 'shared']
        recs = []
        for s in mov:
            p = s['parent']
            pva = int(p.split('_')[1], 16)
            pins = mach.disasm_fn(pva)
            cva = int(s['call_at'], 16)
            idx = [k for k, x in enumerate(pins) if x.address == cva]
            if not idx:
                recs.append(dict(parent=p, call_at=s['call_at'], error='call not in disasm'))
                continue
            i = idx[0]
            got = detect.call_site_base(cs, pins, i)
            r = site_record(mach, cs, pins, i, got or (0, 'none'), pins[i], p)
            r['call_at'] = s['call_at']
            recs.append(r)
        cnt = collections.Counter('error' if 'error' in r else 'ok' for r in recs)
        print(json.dumps(dict(sites=len(recs), by=dict(cnt)), ensure_ascii=False))
        if a.out:
            json.dump(dict(sites=recs), open(a.out, 'w'), ensure_ascii=False, indent=1)
        return
    pva = int(a.parent, 16)
    pins = mach.disasm_fn(pva)
    for i, ins in enumerate(pins):
        if ins.mnemonic != 'call' or not ins.operands or ins.operands[0].type != detect.capstone.CS_OP_IMM:
            continue
        got = detect.call_site_base(cs, pins, i)
        if got is None or got[1] != 'mov':
            continue
        r = site_record(mach, cs, pins, i, got, ins, a.parent)
        print('site 0x%x call 0x%x callee %s' % (ins.address, ins.address, r['callee']))
        for x in r['pre_call']:
            print('   ' + x)
        print('   callee rbp 基準: ' + ', '.join('0x%x:%d:%s' % (x['off'], x['size'], x['kind']) for x in r['callee_access']))


if __name__ == '__main__':
    main()
