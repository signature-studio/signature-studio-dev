#!/usr/bin/env python3
"""vtslots.py — RTTI vtable (work/rtti_vtables.json) から <ns>::<Cls> の slot VA と extent を表示。
Dsp vtable (20 slot): 0 dtor / 7 prepare(float sr) / 13 skip-block? / 14 process(this, ctx, AudioBuffer*) / 15 reset / 17,18,19 補助"""
import json, sys
from fnscan import extent, PDATA
VT = '/home/ubuntu/work/webstudio/tools/targets/kilohearts/work/rtti_vtables.json'
def slots(ns, cls):
    vt = json.load(open(VT))
    return [int(s, 16) for s in vt['.?AV%s@%s@@' % (cls, ns)][0]['slots']]
if __name__ == '__main__':
    cfg = json.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'..','snapins.json')))
    for k, c in cfg.items():
        sl = slots(c['ns'], c['cls'])
        print('==', k)
        for i, s in enumerate(sl):
            if s in (0x1800128a0,) or s < 0x180080000 and s != 0x18004f2a0 and i not in (14,): continue
            e = extent(s)
            print('  slot%-2d %x size=%d calls=%s' % (i, s, e[0] - s, [hex(x) for x in e[1]]))
