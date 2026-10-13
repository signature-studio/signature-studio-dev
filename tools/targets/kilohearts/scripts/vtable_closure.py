#!/usr/bin/env python3
"""ホスト (Snap Heap / Multipass / Phase Plant) の closure を vtable 経由の間接 call で再計算する (KH-19, #782).

規則 (over-approximation, 不動点まで反復):
  1. 初期集合 before = roots (<ns>::*Dsp / *MasterDsp / *DspModel の vtable slot) からの直接 call/jmp 閉包。
  2. 集合内の各関数を逆アセンブルし間接 call を分類する:
       vtable : call [reg+disp] / call [reg] → 候補 = 同 ns の全 class の vtable の slot (disp/8 番目)
       その他 : call reg / call [rip+..] (IAT 以外) / call [idx*s+..] 等 → 解決せず未解決として計上
  3. 候補を閉包に加え、増分が無くなるまで繰り返す。after = 不動点。
  ※ 候補は同 ns の vtable に限る (他 ns・boost/Skia の仮想関数は対象外 = 過小評価の余地あり、REPORT に明記)。
usage: vtable_closure.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <ns> <all|nogui> <out.json>
"""
import sys, json, pickle, re, collections

import pefile
import capstone


def ns_of(cls):
    rest = cls[4:]
    rest = rest[:-2] if rest.endswith('@@') else rest
    if '?' in rest or '$' in rest:
        return None, None
    parts = [p for p in rest.split('@') if p]
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


GUI = re.compile(r'(Editor|Controller|Ui|UI|View|Gui|Skia)')


def vtable_slots(vt, ns, mode):
    """ns の vtable を slot 番号 (0 始まり) ごとに集める。
    mode=all: ns の全 class (上限側) / mode=nogui: GUI 名 (Editor/Controller/UI) を除く (下限側)。"""
    slots = collections.defaultdict(set)
    for cls, lst in vt.items():
        name, cns = ns_of(cls)
        if cns != ns or (mode == 'nogui' and GUI.search(name or '')):
            continue
        for v in lst:
            for k, s in enumerate(v['slots']):
                slots[k].add(int(s, 16))
    return slots


def classify_call(ops):
    if ops.startswith('0x'):
        return ('direct', None)
    if re.fullmatch(r'r[a-z0-9]+', ops):
        return ('reg', None)
    if 'rip' in ops:
        return ('rip_data', None)
    m = re.fullmatch(r'qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]', ops)
    if m:
        d = m.group(2)
        return ('vtable', 0 if d is None else int(d, 16) if d.startswith('0x') else int(d))
    if '+' in ops and ops.count('+') >= 2 or '*' in ops:
        return ('indexed', None)
    return ('other', None)


def main(corep, cgp, vtp, ns, mode, outp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    roots = set()
    for cls, lst in vt.items():
        name, cns = ns_of(cls)
        if cns != ns or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                roots.add(int(s, 16) - base)
    roots = {r for r in roots if r in res}
    slots = vtable_slots(vt, ns, mode)

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

    sites = {}

    def sites_of(f):
        if f not in sites:
            size = res[f]['size']
            off = f - t.VirtualAddress
            sites[f] = [classify_call(i.op_str) for i in md.disasm(data[off:off + size], base + f) if i.mnemonic == 'call']
        return sites[f]

    before = direct_closure(roots)
    cur = set(before)
    done_expand = set()
    while True:
        added = set()
        for f in list(cur):
            if f in done_expand:
                continue
            done_expand.add(f)
            for kind, disp in sites_of(f):
                if kind == 'vtable':
                    for tgt in slots.get(disp // 8, ()):
                        if tgt - base in res and tgt - base not in cur:
                            added.add(tgt - base)
        if not added:
            break
        cur |= direct_closure(added)

    unresolved = collections.Counter()
    vt_sites = 0
    for f in cur:
        for kind, _ in sites_of(f):
            if kind == 'vtable':
                vt_sites += 1
            elif kind != 'direct':
                unresolved[kind] += 1

    def bytes_of(s):
        return sum(res[f]['size'] for f in s)

    result = dict(
        ns=ns, mode=mode, roots=len(roots), candidate_slots=sum(len(v) for v in slots.values()),
        before_funcs=len(before), before_bytes=bytes_of(before),
        after_funcs=len(cur), after_bytes=bytes_of(cur),
        vtable_sites=vt_sites, unresolved=dict(unresolved),
    )
    json.dump(result, open(outp, 'w'), indent=1)
    print(json.dumps(result))


if __name__ == '__main__':
    main(*sys.argv[1:7])
