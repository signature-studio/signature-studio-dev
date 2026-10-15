#!/usr/bin/env python3
# M6 #2: win64 側 DSP 閉包走査 (root: ctor / processReplacing / resume / setParameter ...)
# → root から direct-call closure (.pdata 境界; 分割レコード合体)
# 出力: work/ott_closure.json + work/ott_ranges.txt (RetDec --select-ranges 用)
import sys, os, json, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis
from collections import defaultdict, deque

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
OUT_JSON = os.path.join(BASE, 'work', 'ott_closure.json')
OUT_RANGES = os.path.join(BASE, 'work', 'ott_ranges.txt')

# seed (vtable/COL 由来に確定したもの; ott_match4 の mapping 整合)
ROOTS = {
    'OTTProcessor_ctor':  (0x11d400, 'OTTProcessor ctor (vftable 0x203bd0 + XTtv magic)'),
    'AudioEffectX_ctor':  (0x126920, 'AudioEffectX ctor (magic 0x56737450)'),
    'processReplacing':   (0x11ec20, 'processReplacing (この後 0x11ec49+7080 の分割レコード合体)'),
    'resume':             (0x120800, 'resume'),
    'setParameter':       (0x120af0, 'setParameter 候補 (switch 0..19)'),
    'getParameter':       (0x11e5a0, 'getParameter 候補 (switch 0..0x1e)'),
    'setProgram':         (0x120d10, 'setProgram 候補'),
    'getEditor?':         (0x11c9f0, 'getEditor? (lea rax [rcx+0x30])'),
    'PCS_a':              (0x11cc90, 'ProcessCompSettings? 候補'),
    'PCS_b':              (0x11ebb0, 'PCS_b?'),
    'PCS_c':              (0x11eae0, 'PCS_c?'),
    'PCS_d':              (0x11eaf0, 'PCS_d? setProgramName'),
    'PCS_e':              (0x11e770, 'getProgram 検出?'),
    'PCS_f':              (0x11e7b0, 'getParameterLabel'),
    'PCS_g':              (0x11e820, 'getParameterName'),
}

W = Bin(WINF)
D = Dis(W)
BYP = {a: (a, s) for (a, s) in W.fns}


def sz(rva):
    e = BYP.get(rva)
    if e:
        return e[1]
    return 0


def main():
    seeds = []
    for (rva, note) in ROOTS.values():
        szv = ((0x11ec49 + 7080) - rva) if rva == 0x11ec20 else sz(rva)
        seeds.append((rva, szv))
    print('[scan] seeds:', [(hex(0x400000 + a), s) for (a, s) in seeds])
    closure, externs, indirects = {}, {}, defaultdict(int)
    q = deque(seeds)
    while q:
        (rva, szv) = q.popleft()
        if rva in closure:
            continue
        closure[rva] = szv
        f = D.features(rva, szv)
        if f is None:
            print('[!] features Niet: 0x%x' % rva)
            continue
        for c in set(f['calls']):
            if c in closure:
                continue
            csz = sz(c)
            if csz > 0:
                q.append((c, csz))
            else:
                externs[c] = 1
        if f['indirect']:
            indirects[rva] += f['indirect']
    tot = sum(closure.values())
    print('[scan] closure fns: %d, code bytes: %d, externs: %d' % (len(closure), tot, len(externs)))
    for rva in sorted(externs):
        print('    EXTERN: 0x%x (V → addr=0x%x)' % (0x400000 + rva, 0x400000 + rva))
    rngs = ['0x%x-0x%x' % (0x180000000 + rva, 0x180000000 + rva + closure[rva]) for rva in sorted(closure)]
    open(OUT_RANGES, 'w').write(','.join(rngs))
    json.dump({'fn_count': len(closure), 'code_bytes': tot,
               'externs': sorted(hex(0x400000 + r) for r in externs),
               'indirect_calls': {hex(0x400000 + k): v for k, v in indirects.items()},
               'fns': {hex(0x400000 + k): v for k, v in sorted(closure.items())}},
              open(OUT_JSON, 'w'), indent=1)
    print('[scan] wrote', OUT_RANGES)
    for rva in sorted(closure):
        print('   fn 0x%x size %d' % (0x400000 + rva, closure[rva]))


if __name__ == '__main__':
    main()
