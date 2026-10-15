#!/usr/bin/env python3
"""#3727 受入 2: 0x10d3a30 の入口 (条件 g1 ≠ 0x7fffffff または g2 ≠ 0) に届く経路を、0x11fc770 の呼出し元まで遡る (読取専用・静的)。

0x10d3a30 の直接呼出し元 → 0x11fc770 の直接呼出し元 → その呼出し元の直接呼出し元、を rel32 の call (E8) で全件列挙する。
間接 call (call qword [...]) は対象外 (呼出し元を静的に決められないため、件数だけ数える)。

usage: python probe_1414_callers.py --write   (要 FL_WIN64_DIR・venv: tools/startup/license_obs/env.sh)
出力: results/probe_1414_callers.json (--write 時)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from peidx import Image  # noqa: E402

TARGETS = [0x10d3a30, 0x11fc770]


def direct_callers(img, target):
    out = []
    for lo, hi, insns in img.iter_insns():
        for ins in insns:
            if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
                if int(ins.op_str, 16) == target:
                    fn = img.func_of(ins.address)
                    out.append({'at': hex(ins.address), 'func': hex(fn) if fn else None})
    return out


def run_dyn(addrs):
    from unicorn import UC_HOOK_CODE
    from emu_reg import Emu, Reg
    from run_cases import seed_license
    from probe_1414 import CASES
    out = []
    for name, kw, cl in CASES:
        r = Reg()
        seed_license(r, **kw)
        e = Emu(r)
        e.setup_globals()
        e.init_units()
        hits = {}
        for a in addrs:
            def cb(uc, ad, s, ud, a=a):
                hits[hex(a)] = hits.get(hex(a), 0) + 1
            e.uc.hook_add(UC_HOOK_CODE, cb, begin=a, end=a)
        st = e.run(cl=cl)
        out.append({'case': name, 'status': st if st == 'ok' else st[:120], 'hits': hits})
    return out


def main():
    img = Image()
    res = {}
    for t in TARGETS:
        cs = direct_callers(img, t)
        res[hex(t)] = {'direct_callers': cs, 'n': len(cs)}
        print(hex(t), 'direct callers:', len(cs))
        for c in cs:
            print('  ', c)
    up = {}
    for c in res[hex(0x11fc770)]['direct_callers']:
        if c['func']:
            ups = direct_callers(img, int(c['func'], 16))
            up[c['func']] = ups
            print('UP', c['func'], 'callers:', len(ups), [u['func'] for u in ups][:10])
    res['callers_of_0x11fc770_callers'] = up
    if '--dyn' in sys.argv:
        res['dyn'] = run_dyn([0x10d3a30, 0x11fc770, 0xc4dba0, 0xd18130, 0xed7c00, 0x10c7cd0])
        for d in res['dyn']:
            print('DYN', d)
    if '--write' in sys.argv:
        os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
        with open(os.path.join(HERE, 'results', 'probe_1414_callers.json'), 'w') as f:
            json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
