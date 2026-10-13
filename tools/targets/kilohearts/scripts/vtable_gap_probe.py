#!/usr/bin/env python3
"""KH-19b (#848) 計測用: 対照 ns の before (直接 call 閉包) 内の vtable 間接 call について、
(1) 候補 (全 class の同 slot) のうち before 外に出る割合、(2) 呼び出し直前に rcx (this) へ書く命令の種類、を 1 行 JSON で出す。
rcx の書き手は同一関数内の直前命令だけを見る (分岐・ループ跨ぎは見ない)。
usage: vtable_gap_probe.py <HeartCore.core_64> <callgraph.pkl> <rtti_vtables.json> <ns>
"""
import sys, json, pickle, collections, re
import pefile
import capstone
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

    roots = set()
    allslots = collections.defaultdict(set)
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != ns:
            continue
        for v in lst:
            for k, s in enumerate(v['slots']):
                allslots[k].add(int(s, 16) - base)
            if re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
                for s in v['slots']:
                    roots.add(int(s, 16) - base)
    roots = {r for r in roots if r in res}

    seen, st = set(), list(roots)
    while st:
        f = st.pop()
        if f in seen or f not in res:
            continue
        seen.add(f)
        st.extend(res[f]['calls'])
        st.extend(res[f]['jmps'])

    stats = collections.Counter()
    for f in seen:
        size = res[f]['size']
        off = f - t.VirtualAddress
        ins = list(md.disasm(data[off:off + size], base + f))
        for idx, i in enumerate(ins):
            if i.mnemonic != 'call':
                continue
            kind, disp = vc.classify_call(i, iat)
            if kind != 'vtable':
                continue
            stats['vtable_sites'] += 1
            cand = {c for c in allslots.get(disp // 8, ()) if c in res}
            stats['cand_total'] += len(cand)
            stats['cand_outside_before'] += len(cand - seen)
            if cand - seen:
                stats['sites_with_outside_cand'] += 1
            src = None
            for j in range(idx - 1, -1, -1):
                p = ins[j]
                if p.mnemonic in ('ret', 'jmp', 'call', 'je', 'jne', 'jz', 'jnz', 'ja', 'jb', 'jbe', 'jae', 'jl', 'jg'):
                    break
                ops = p.op_str.split(', ')
                if len(ops) == 2 and re.fullmatch(r'r?cx|ecx|rcx', ops[0]) and p.mnemonic in ('mov', 'lea'):
                    src = p
                    break
            if src is None:
                stats['rcx_writer_not_found'] += 1
            elif src.mnemonic == 'lea' and 'rip' in src.op_str:
                stats['rcx_from_lea_rip'] += 1
            elif src.mnemonic == 'mov' and re.fullmatch(r'r[a-z0-9]+', src.op_str.split(', ')[1]):
                stats['rcx_from_reg_mov'] += 1
            else:
                stats['rcx_from_other'] += 1
    print(json.dumps(dict(ns=ns, before_funcs=len(seen), **stats)))


if __name__ == '__main__':
    main(*sys.argv[1:5])
