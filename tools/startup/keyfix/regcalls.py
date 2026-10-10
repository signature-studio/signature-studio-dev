#!/usr/bin/env python3
"""regcalls.py — Reg* への到達 site を抽出 (IAT jmp thunk 経由含む) → 関数単位に集約

出力: work/reg_funcs.json  {func_hex: {api: [site_hex,...]}}
     work/reg_sites_all.tsv  func\tsite\tapi\ttarget
"""
import sys, re, json, os, collections
import feparse as F
import fnindex

RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')


def reg_iat_map():
    iat = F.iat_names()
    return {va: n.split('!')[-1] for va, n in iat.items() if n.lower().startswith('advapi32')}


def build(force=False):
    jf = os.path.join(WORK, 'reg_funcs.json')
    if os.path.exists(jf) and not force:
        return json.load(open(jf))
    F.load()
    reg_iat = reg_iat_map()
    tva, tsize = F.text_range()
    off = F.va2off(tva)
    data = F._RAW[off:off + tsize]
    # pass 1: IAT への rip 相対 jmp (thunk) を集める
    thunk = {}  # thunk_va -> api
    for ins in F.md().disasm(data, tva):
        m = RE_RIP.search(ins.op_str)
        if not m or ins.mnemonic != 'jmp':
            continue
        disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
        tgt = ins.address + ins.size + disp
        api = reg_iat.get(tgt)
        if api:
            thunk[ins.address] = api
    # pass 2: E8 call → thunk / または直接 rip-rel call → IAT
    funcs_by_api = collections.defaultdict(lambda: collections.defaultdict(list))
    sites = []
    g = F.build_call_graph()
    for target, site_list in g.items():
        api = thunk.get(target)
        if not api:
            continue
        for site in site_list:
            f = fnindex.func_of(site)
            fs = f[0] if f else 0
            funcs_by_api[hex(fs)][api].append(hex(site))
            sites.append((fs, site, api, target))
    for thunk_va, api in thunk.items():
        pass
    json.dump(funcs_by_api, open(jf, 'w'), indent=0)
    with open(os.path.join(WORK, 'reg_sites_all.tsv'), 'w') as fh:
        for fs, site, api, tgt in sorted(sites):
            fh.write('%x\t%x\t%s\t%x\n' % (fs, site, api, tgt))
    return funcs_by_api


if __name__ == '__main__':
    fb = build(force='--force' in sys.argv)
    cnt = collections.Counter()
    n = 0
    for d in fb.values():
        for a, v in d.items():
            cnt[a] += len(v)
            n += len(v)
    print('functions touching Reg*:', len(fb), 'sites:', n)
    for a, c in sorted(cnt.items(), key=lambda t: -t[1]):
        print('%-24s %d' % (a, c))
