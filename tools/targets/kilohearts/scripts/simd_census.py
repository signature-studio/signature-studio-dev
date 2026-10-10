#!/usr/bin/env python3
"""snap-in 固有 closure の SIMD mnemonic 集計 + 既存 m6 helper (msimd6.c) との被覆比較。

usage: simd_census.py HeartCore.core_64 callgraph.pkl closures_sets.pkl m6_msimd6.c out.json
"""
import sys, re, json, pickle, collections
import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64


def main(path, cgp, setp, m6c, outp):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    t = pe.sections[0]
    cg = pickle.load(open(cgp, 'rb'))['res']
    S = pickle.load(open(setp, 'rb'))
    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    have = set(re.findall(r'__asm_([a-z0-9_]+?)(?:__\d+)?\(', open(m6c).read()))
    have |= set(re.findall(r'__asm_([a-z0-9]+)', open(m6c).read()))
    res = {}
    allm = collections.Counter()
    for ns, funcs in S['sets'].items():
        cnt = collections.Counter()
        for f in funcs:
            sz = cg[f]['size']
            off = t.PointerToRawData + (f - t.VirtualAddress)
            for a, s, mn, ops in md.disasm_lite(data[off:off + sz], base + f):
                if ('xmm' in ops or 'ymm' in ops or 'zmm' in ops or mn.startswith('v')) and mn not in ('push', 'pop', 'call', 'jmp', 'ret', 'vzeroupper'):
                    cnt[mn] += 1
        res[ns] = dict(cnt)
        allm.update(cnt)
    miss = {m: c for m, c in allm.items() if m not in have}
    out = {'per_ns': {ns: {'distinct': len(c), 'total': sum(c.values()), 'uncovered': sorted(m for m in c if m not in have),
                           'uncovered_n': sum(v for m, v in c.items() if m not in have)} for ns, c in res.items()},
           'global_distinct': len(allm), 'global_uncovered': len(miss), 'm6_helper_names': len(have),
           'top_uncovered': sorted(miss.items(), key=lambda x: -x[1])[:40], 'top_all': allm.most_common(40)}
    json.dump(out, open(outp, 'w'), indent=1)
    print('global distinct mnemonics', len(allm), 'uncovered by m6 helpers', len(miss), 'm6 helper names', len(have))


if __name__ == '__main__':
    main(*sys.argv[1:6])
