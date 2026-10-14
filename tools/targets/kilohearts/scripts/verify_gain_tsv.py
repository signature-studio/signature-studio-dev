#!/usr/bin/env python3
"""gain_before_160.tsv の各行を、バイト列から独立に照合する (KH-19f, #1816).

検査:
 A. root 行 (root_class 非空): func_rva が gain の *Dsp/*MasterDsp/*DspModel の vtable slot に載る
 B. 非 root 行: parent_rva の関数内に call_site_rva の命令があり、call/jmp rel が func_rva を指す
 C. 情報: func_rva が .pdata の BeginAddress と一致する行数 (不一致は leaf sweep で拾った関数。判定には使わない)
 D. parent は TSV 内にあり、辿ると root に達する
出力は 1 行 JSON。機械照合であり、手検証 (verified=manual) の代替ではない。
usage: verify_gain_tsv.py <HeartCore.core_64> <callgraph.pkl> <rtti_vtables.json> <tsv>
"""
import sys, json, pickle, re, csv

import pefile
import capstone
sys.path.insert(0, __import__('os').path.dirname(__file__))
import vtable_closure as vc


def main(corep, cgp, vtp, tsvp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    res = pickle.load(open(cgp, 'rb'))['res']
    vt = json.load(open(vtp))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    pdata = set()
    for e in pe.DIRECTORY_ENTRY_EXCEPTION:
        pdata.add(e.struct.BeginAddress)

    root_slots = {}
    for cls, lst in vt.items():
        name, cns = vc.ns_of(cls)
        if cns != 'gain' or not re.search(r'(MasterDsp|Dsp|DspModel)$', name or ''):
            continue
        for v in lst:
            for s in v['slots']:
                root_slots.setdefault(int(s, 16) - base, cls)

    rows = list(csv.DictReader(open(tsvp), delimiter='\t'))
    by = {int(r['func_rva'], 16): r for r in rows}
    c = {'rows': len(rows), 'A_root_ok': 0, 'A_fail': [], 'B_call_ok': 0, 'B_fail': [],
         'C_pdata_ok': 0, 'C_fail': [], 'D_chain_ok': 0, 'D_fail': []}

    for f, r in by.items():
        if f in pdata:
            c['C_pdata_ok'] += 1
        if r['root_class']:
            if f in root_slots and root_slots[f] == r['root_class']:
                c['A_root_ok'] += 1
            else:
                c['A_fail'].append(hex(f))
            continue
        p = int(r['parent_rva'], 16)
        cs = int(r['call_site_rva'], 16)
        ok = False
        if p in res:
            off = p - t.VirtualAddress
            for i in md.disasm(data[off:off + res[p]['size']], base + p):
                if i.address - base == cs:
                    if i.mnemonic in ('call', 'jmp') and i.op_str.startswith('0x'):
                        ok = (int(i.op_str, 16) - base == f)
                    break
        if ok:
            c['B_call_ok'] += 1
        else:
            c['B_fail'].append(hex(f))

    for f, r in by.items():
        seen = set()
        cur = f
        good = False
        while True:
            rr = by.get(cur)
            if rr is None or cur in seen:
                break
            seen.add(cur)
            if rr['root_class']:
                good = True
                break
            cur = int(rr['parent_rva'], 16)
        if good:
            c['D_chain_ok'] += 1
        else:
            c['D_fail'].append(hex(f))

    for k in ('A_fail', 'B_fail', 'C_fail', 'D_fail'):
        c[k] = c[k][:20] + ([] if len(c[k]) <= 20 else ['...'])
    print(json.dumps(c, ensure_ascii=False))


if __name__ == '__main__':
    main(*sys.argv[1:5])
