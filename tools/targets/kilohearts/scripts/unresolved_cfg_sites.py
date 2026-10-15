#!/usr/bin/env python3
"""CFG/XFG dispatch 経由 call のうち rax 出所が未確定 (vtable_cfg / lea_fn / lea_nonfn / rip_load 以外) の site を列挙する (#3363 / KH-55)。

閉包は vtable_closure.py の after_cfg と同じ不動点 (vtable 規則 + vtable_cfg + lea_fn) で求める。
各 site について、直前の rax 書き込み命令と、直前の call (あれば) の呼び先種別を出す。
usage: unresolved_cfg_sites.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <ns> <all|nogui> <out.json>
"""
import sys, json, pickle, collections

import pefile
import capstone

import vtable_closure as vc

RESOLVED = ('vtable_cfg', 'lea_fn', 'lea_nonfn', 'rip_load')


def callee_of(insn, iat):
    kind, arg = vc.classify_call(insn, iat)
    if kind == 'rip_data':
        return 'rip_data:' + hex(arg)
    if kind == 'iat':
        return 'iat'
    return kind


def preceding_call(ins, k):
    """site 直前の call (rax 書き込みより前) の呼び先種別。rax 書き込みで止まる場合のみ見る。"""
    j = k - 1
    while j >= 0:
        w = ins[j]
        if w.mnemonic == 'call':
            return w
        ops = [o.strip() for o in w.op_str.split(',')] if w.op_str else []
        if ops and ops[0] in vc.RAX_NAMES and w.mnemonic not in ('cmp', 'test', 'push', 'bt'):
            return None
        j -= 1
    return None


def main(corep, cgp, vtp, ns, mode, outp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    iat = vc.iat_slots(pe, base)
    cfg = vc.cfg_dispatch_slots(pe)
    slots = vc.vtable_slots(vt, ns, mode)

    roots = set()
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != ns or not vc.re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
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

    def disasm(f):
        size = res[f]['size']
        off = f - t.VirtualAddress
        return list(md.disasm(data[off:off + size], base + f))

    before = direct_closure(roots)
    cur, done = set(before), set()
    while True:
        added = set()
        for f in list(cur):
            if f in done:
                continue
            done.add(f)
            ins = disasm(f)
            for k, i in enumerate(ins):
                if i.mnemonic != 'call':
                    continue
                kind, disp = vc.classify_call(i, iat)
                if kind == 'vtable':
                    for tgt in slots.get(disp // 8, ()):
                        if tgt - base in res and tgt - base not in cur:
                            added.add(tgt - base)
                elif vc.is_cfg_call(i, cfg):
                    rk, arg = vc.rax_source(ins, k, base, res)
                    if rk == 'vtable_cfg':
                        for tgt in slots.get(arg // 8, ()):
                            if tgt - base in res and tgt - base not in cur:
                                added.add(tgt - base)
                    elif rk == 'lea_fn' and arg - base not in cur:
                        added.add(arg - base)
        if not added:
            break
        cur |= direct_closure(added)

    out = []
    for f in sorted(cur):
        ins = disasm(f)
        for k, i in enumerate(ins):
            if i.mnemonic != 'call' or not vc.is_cfg_call(i, cfg):
                continue
            rk, arg = vc.rax_source(ins, k, base, res)
            if rk in RESOLVED:
                continue
            prev = preceding_call(ins, k)
            out.append(dict(
                fn=hex(base + f), site=hex(i.address), kind=rk,
                arg=None if arg is None else hex(arg),
                preceding_call=None if prev is None else callee_of(prev, iat),
            ))
    json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(dict(ns=ns, mode=mode, unresolved=len(out),
                          by_kind=dict(collections.Counter(o['kind'] for o in out)))))


if __name__ == '__main__':
    main(*sys.argv[1:7])
