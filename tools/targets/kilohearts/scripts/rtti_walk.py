#!/usr/bin/env python3
"""MSVC x64 RTTI walker for HeartCore.core_64.

TypeDescriptor (".?AV..") -> CompleteObjectLocator (x64: 6 dwords, RVA based)
-> vtable (qword COL ptr followed by function ptrs) -> per-entry function size via .pdata.
Output: JSON {class: [{vtable, nslots, slots:[va...], sizes:[...]}]} + summary by namespace.

usage: rtti_walk.py HeartCore.core_64 out.json
"""
import sys, json, re, collections, struct
import numpy as np
import pefile


def main(path, out):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    secs = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
    text = secs['.text']
    t_lo, t_hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

    def img(sec):
        return data[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]

    # .pdata -> function table (begin,end)
    pd = secs['.pdata']
    pdb = img(pd)
    n = pd.Misc_VirtualSize // 12
    pdarr = np.frombuffer(pdb[:n * 12], dtype='<u4').reshape(-1, 3)
    fbeg, fend = pdarr[:, 0].copy(), pdarr[:, 1].copy()
    order = np.argsort(fbeg)
    fbeg, fend = fbeg[order], fend[order]

    def fsize(rva):
        i = np.searchsorted(fbeg, rva)
        if i < len(fbeg) and fbeg[i] == rva:
            return int(fend[i] - fbeg[i])
        return None

    # TypeDescriptors: scan for ".?A[VU]" strings in .data (MSVC places type_info in .data)
    td = {}  # rva(typedesc) -> name
    for sname in ('.data', '.rdata'):
        s = secs[sname]
        b = img(s)
        for m in re.finditer(rb'\.\?A[VU][\x21-\x7e]+?@@\x00', b):
            off = m.start() - 16
            if off < 0:
                continue
            td[s.VirtualAddress + off] = m.group(0)[:-1].decode()
    print('typedescriptors', len(td), file=sys.stderr)

    # COLs: 6 dwords [1, off, cdoff, td_rva, cd_rva, self_rva]
    cols = {}  # col_rva -> (name, offset)
    for sname in ('.rdata',):
        s = secs[sname]
        b = img(s)
        a = np.frombuffer(b[:len(b) // 4 * 4], dtype='<u4')
        idx = np.nonzero(a[:-5] == 1)[0]
        tdset = set(td.keys())
        for i in idx:
            if int(a[i + 3]) in tdset:
                col_rva = s.VirtualAddress + int(i) * 4
                if int(a[i + 5]) == col_rva:
                    cols[col_rva] = (td[int(a[i + 3])], int(a[i + 1]))
    print('COLs', len(cols), file=sys.stderr)

    # vtables: qword == base+col_rva
    vt = collections.defaultdict(list)
    colva = {base + k: k for k in cols}
    for sname in ('.rdata',):
        s = secs[sname]
        b = img(s)
        q = np.frombuffer(b[:len(b) // 8 * 8], dtype='<u8')
        for i in np.nonzero(np.isin(q, np.fromiter(colva.keys(), dtype='<u8')))[0]:
            col_rva = colva[int(q[i])]
            name, off = cols[col_rva]
            slots = []
            j = i + 1
            while j < len(q):
                v = int(q[j])
                r = v - base
                if t_lo <= r < t_hi and r != 0:
                    slots.append(r)
                    j += 1
                else:
                    break
            vt[name].append({'vtable_rva': s.VirtualAddress + (int(i) + 1) * 8, 'col_off': off, 'slots': slots})
    res = {}
    for name, lst in vt.items():
        res[name] = []
        for v in lst:
            sizes = [fsize(r) for r in v['slots']]
            res[name].append({'vtable': hex(base + v['vtable_rva']), 'off': v['col_off'], 'nslots': len(v['slots']),
                              'slots': [hex(base + r) for r in v['slots']], 'sizes': sizes})
    json.dump(res, open(out, 'w'), indent=0)
    print('classes with vtables', len(res), file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
