#!/usr/bin/env python3
"""KH-19b (#848) 計測用: vtable 間接 call の受け手 (this) 型を 1 段追う closure 試行 (narrow)。

wide = 従来 (同 ns の全 class の同 slot 番号)。narrow = 呼び出し元関数の一意な所有 class の slot のみ。
所有 class が一意でない関数・vtable に載らない関数は wide に落とす。出力は 1 行 JSON。
usage: vtable_probe_this.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <ns>
"""
import sys, json, pickle, re, collections
import capstone
import pefile
import vtable_closure as vc


def main(corep, cgp, vtp, ns):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    iat = vc.iat_slots(pe, base)

    owners = collections.defaultdict(set)
    cls_slots = collections.defaultdict(lambda: collections.defaultdict(set))
    allslots = collections.defaultdict(set)
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        for v in lst:
            for k, s in enumerate(v['slots']):
                owners[int(s, 16) - base].add(cls)
                if cns == ns:
                    cls_slots[cls][k].add(int(s, 16) - base)
                    allslots[k].add(int(s, 16) - base)

    roots = set()
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != ns or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                roots.add(int(s, 16) - base)
    roots = {r for r in roots if r in res}

    def direct_closure(seed):
        seen, st = set(), list(seed)
        while st:
            f = st.pop()
            if f in seen or f not in res:
                continue
            seen.add(f)
            st.extend(res[f]['calls'])
            st.extend(res[f]['jmps'])
        return seen

    def owner_of(f):
        own = [c for c in owners.get(f, ()) if vc.ns_of(c)[1] == ns]
        return own[0] if len(own) == 1 else None

    sites = {}

    def sites_of(f):
        if f not in sites:
            size = res[f]['size']
            off = f - t.VirtualAddress
            sites[f] = [vc.classify_call(i, iat) for i in md.disasm(data[off:off + size], base + f) if i.mnemonic == 'call']
        return sites[f]

    before = direct_closure(roots)
    cur = set(before)
    done = set()
    kinds = collections.Counter()
    while True:
        added = set()
        for f in list(cur):
            if f in done:
                continue
            done.add(f)
            oc = owner_of(f)
            for kind, disp in sites_of(f):
                if kind != 'vtable':
                    continue
                k = disp // 8
                if oc is not None:
                    kinds['narrow'] += 1
                    tg = cls_slots[oc].get(k, set())
                else:
                    kinds['wide'] += 1
                    tg = allslots.get(k, set())
                added |= {a for a in tg if a in res and a not in cur}
        if not added:
            break
        cur |= direct_closure(added)

    print(json.dumps(dict(ns=ns, before_funcs=len(before), after_narrow_funcs=len(cur),
                          vtable_sites=dict(kinds))))


if __name__ == '__main__':
    main(*sys.argv[1:5])
