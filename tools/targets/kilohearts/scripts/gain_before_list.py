#!/usr/bin/env python3
"""対照 ns (gain) の before 集合 (roots の直接 call/jmp 閉包) を 1 関数 1 行で出す (KH-19e, #1619).

各関数について、閉包に入る根拠 (root からの呼び出し鎖の親と call 位置) を付ける。
出力は機械生成であり、人手検証の結果ではない (列 verified は常に auto)。
usage: gain_before_list.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <ns> <out.tsv>
"""
import sys, json, pickle, re, collections

import pefile
import capstone
import vtable_closure as vc


def main(corep, cgp, vtp, ns, outp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    roots = {}
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != ns or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                r = int(s, 16) - base
                if r in res:
                    roots.setdefault(r, (cls, name))

    parent = {}
    st = list(roots)
    for r in roots:
        parent[r] = None
    while st:
        f = st.pop()
        for g in res[f]['calls'] + res[f]['jmps']:
            if g in res and g not in parent:
                parent[g] = f
                st.append(g)

    def call_site(caller, callee):
        off = caller - t.VirtualAddress
        for i in md.disasm(data[off:off + res[caller]['size']], base + caller):
            if i.mnemonic in ('call', 'jmp') and i.op_str.startswith('0x'):
                if int(i.op_str, 16) - base == callee:
                    return i.address - base
        return None

    with open(outp, 'w') as fh:
        fh.write('func_rva\tsize\troot_class\tparent_rva\tcall_site_rva\tverified\n')
        for f in sorted(parent):
            p = parent[f]
            cs = call_site(p, f) if p is not None else None
            rc = roots.get(f, (None, None))[0] if f in roots else ''
            fh.write('%#x\t%d\t%s\t%s\t%s\tauto\n' % (
                f, res[f]['size'], rc or '',
                '%#x' % p if p is not None else '',
                '%#x' % cs if cs is not None else ''))
    print(json.dumps({'ns': ns, 'before_funcs': len(parent), 'roots': len(roots)}))


if __name__ == '__main__':
    main(*sys.argv[1:6])
