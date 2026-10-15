#!/usr/bin/env python3
"""#4764: 0x10c7cd0 の間接 call (静的 298 件) の実行サイト和集合を、ライセンス入力を増やして測る (読取専用)。

probe_1414_tables.py --dyn の 6 入力 (dyn_union 41) に、run_cases.py の入力変種 (GUID・ComputerName・
AppData・IL の長さ・cl) を足す。増えなければ、未実行 257 件はライセンス入力では到達しないことを示す。
usage: python probe_4764_widen.py --write   (要 FL_WIN64_DIR・venv: tools/startup/license_obs/env.sh)
出力: results/probe_4764_widen.json (--write 時)
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from unicorn import UC_HOOK_CODE  # noqa: E402
from emu_reg import Emu, Reg  # noqa: E402
from run_cases import seed_license, GUID_A  # noqa: E402
from probe_1414 import indirect_sites  # noqa: E402
from peidx import Image  # noqa: E402

GD = 'ffffffff-0000-1111-2222-333344445555'
APP = 'C:\\Users\\u\\AppData\\Roaming'
HEX128 = '0123456789ABCDEF' * 8
CASES = (
    ('A1 no-IL cl0', dict(drop_il=True), 0, 'PC1', APP, GUID_A),
    ('A2 no-IL cl1', dict(drop_il=True), 1, 'PC1', APP, GUID_A),
    ('A2b no-IL cl2', dict(drop_il=True), 2, 'PC1', APP, GUID_A),
    ('A3 no-IL other-PC', dict(drop_il=True, guid=GD), 0, 'OTHER-PC', 'D:\\x\\Roaming', GD),
    ('A4 no-IL no-GUID', dict(drop_il=True, drop_guid=True), 0, 'PC1', APP, None),
    ('B1 seed cl0', dict(), 0, 'PC1', APP, GUID_A),
    ('B2 seed cl1', dict(), 1, 'PC1', APP, GUID_A),
    ('B2b seed cl2', dict(), 2, 'PC1', APP, GUID_A),
    ('B3 seed other-PC', dict(guid=GD), 0, 'OTHER-PC', 'D:\\x\\Roaming', GD),
    ('D1 128hex cl1', dict(il_override=HEX128), 1, 'PC1', APP, GUID_A),
    ('D2 empty cl1', dict(il_override=''), 1, 'PC1', APP, GUID_A),
    ('D3 8hex cl0', dict(il_override='3a00ff7e'), 0, 'PC1', APP, GUID_A),
    ('D3 8hex cl1', dict(il_override='3a00ff7e'), 1, 'PC1', APP, GUID_A),
)


def main():
    img = Image()
    sites = indirect_sites(img)
    static = {hex(a) for a, _, _, _ in sites}
    union = set()
    rows = []
    for name, kw, cl, comp, appdata, _guid in CASES:
        t0 = time.time()
        r = Reg()
        seed_license(r, **kw)
        e = Emu(r, comp=comp, appdata=appdata)
        e.setup_globals()
        e.init_units()
        seen = set()
        for addr, size, op, md in sites:
            def cb(uc, a, s, ud, addr=addr):
                seen.add(hex(addr))
            e.uc.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)
        st = e.run(cl=cl)
        new = seen - union
        union |= seen
        rows.append({'case': name, 'status': st if st == 'ok' else st[:120], 'sites_executed': len(seen),
                     'new_vs_previous': len(new), 'union_so_far': len(union), 'sec': round(time.time() - t0, 1)})
        print(rows[-1], flush=True)
    res = {'static_sites': len(static), 'executed_union': len(static & union),
           'unexecuted': len(static - union), 'cases': rows}
    print('static', res['static_sites'], 'executed_union', res['executed_union'], 'unexecuted', res['unexecuted'])
    if '--write' in sys.argv:
        os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
        with open(os.path.join(HERE, 'results', 'probe_4764_widen.json'), 'w') as f:
            json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
