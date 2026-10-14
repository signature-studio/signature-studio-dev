#!/usr/bin/env python3
"""対照 Gain の before 一覧 (gain_before_160.tsv 形式) の機械照合 (KH-19g, #2098).

これは人手検証ではない。手検証の代わりに結果を書かないこと (verified 列は変更しない)。
検査内容:
  1. root 行の root_class が vtable slot に実在する (rtti_vtables.json の gain ns の slot と一致)
  2. 非 root 行の (parent_rva, call_site_rva) で親の命令が func_rva を direct call/jmp している
  3. 一覧の before 件数が vtable_closure.py の before_funcs と一致する (呼び出し側で比較)
usage: gain_mech_check.py <HeartCore.core_64> <work/callgraph.pkl> <work/rtti_vtables.json> <gain_before_160.tsv>
"""
import csv, json, pickle, re, sys

import pefile
import capstone
import vtable_closure as vc


def main(corep, cgp, vtp, tsvp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    slots = {}
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != 'gain' or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                slots.setdefault(int(s, 16) - base, set()).add(cls)

    rows = list(csv.DictReader(open(tsvp), delimiter='\t'))
    roots = ok_root = nonroot = ok_edge = 0
    bad = []
    for r in rows:
        f = int(r['func_rva'], 16)
        if not r['parent_rva']:
            roots += 1
            if r['root_class'] and r['root_class'] in slots.get(f, set()):
                ok_root += 1
            else:
                bad.append(('root', r['func_rva'], r['root_class']))
            continue
        nonroot += 1
        p = int(r['parent_rva'], 16)
        c = int(r['call_site_rva'], 16)
        hit = False
        for i in md.disasm(data[p - t.VirtualAddress:p - t.VirtualAddress + res[p]['size']], base + p):
            if (i.address - base == c and i.mnemonic in ('call', 'jmp')
                    and i.op_str.startswith('0x') and int(i.op_str, 16) - base == f):
                hit = True
        if hit:
            ok_edge += 1
        else:
            bad.append(('edge', r['func_rva'], r['parent_rva'], r['call_site_rva']))
    print(json.dumps({'rows': len(rows), 'roots': roots, 'root_slot_ok': ok_root,
                      'nonroot': nonroot, 'edge_ok': ok_edge, 'bad': bad}))


if __name__ == '__main__':
    main(*sys.argv[1:5])
