#!/usr/bin/env python3
"""MSVC x64 RTTI walker + vtable 抽出 (Massive X.vst3, ImageBase 0x180000000)。

CAB-46 の mx_callgraph.py とは別実装。KN の rtti_walk.py と同じ x64 COL 構造を使うが
本バイナリはセクション構成が違う (.text 0x1000 / .rdata 0x3971000 / .data 0x515f000)。

  TypeDescriptor (".?AV...@@") -> COL (x64: [sig=1, offset, cdOffset, td_rva, cd_rva, self_rva])
    -> vtable (COL への qword の直後に関数ポインタ列)

usage: mx_rtti.py <pe> <out.json>
"""
import sys, json, re, collections, struct
import numpy as np
import pefile


def main(path, out):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    secs = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}

    def img(sec):
        return data[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]

    execs = [s for s in pe.sections if s.Characteristics & 0x20000000]
    text = execs[0] if execs else secs['.text']
    t_lo, t_hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

    # ---- .pdata -> 関数境界 (本 PE は .pdata が 2 つ。大きい方 = x64 本体, 小さい方 = 別 (CFG/shadow))
    pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
                 key=lambda s: -s.Misc_VirtualSize)
    pd = pds[0]
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

    # ---- TypeDescriptor: ".?A[VU]" 名を持つ 16B ヘッダ + name
    td = {}
    for sname in ('.rdata', '.data'):
        s = secs[sname]
        b = img(s)
        for m in re.finditer(rb'\.\?A[VU][\x21-\x7e]+?@@\x00', b):
            off = m.start() - 16
            if off < 0:
                continue
            td[s.VirtualAddress + off] = m.group(0)[:-1].decode()
    print('typedescriptors', len(td), file=sys.stderr)

    # ---- COL: 6 dwords [1, offset, cdOffset, td_rva, cd_rva, self_rva]
    cols = {}
    for sname in ('.rdata', '.data'):
        s = secs[sname]
        b = img(s)
        a = np.frombuffer(b[:len(b) // 4 * 4], dtype='<u4')
        tdset = np.array(sorted(td.keys()), dtype='<u4')
        cand = np.nonzero(a[:-5] == 1)[0]
        # 候補 index を td テーブルで絞る (i+3 が td_rva)
        for i in cand:
            td_rva = int(a[i + 3])
            if td_rva not in td:
                continue
            col_rva = s.VirtualAddress + int(i) * 4
            if int(a[i + 5]) == col_rva:
                cols[col_rva] = (td[td_rva], int(a[i + 1]))
    print('COLs', len(cols), file=sys.stderr)

    # ---- vtable: qword == base+col_rva の直後に関数ポインタ列
    vt = collections.defaultdict(list)
    colva = {base + k: k for k in cols}
    for sname in ('.rdata', '.data'):
        s = secs[sname]
        b = img(s)
        q = np.frombuffer(b[:len(b) // 8 * 8], dtype='<u8')
        hits = np.nonzero(np.isin(q, np.fromiter(colva.keys(), dtype='<u8')))[0]
        for i in hits:
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
            vt[name].append({'vtable_rva': s.VirtualAddress + (int(i) + 1) * 8,
                             'section': sname, 'col_off': off, 'slots': slots})

    res = {}
    for name, lst in sorted(vt.items()):
        res[name] = [{'vtable': hex(base + v['vtable_rva']), 'section': v['section'],
                      'off': v['col_off'], 'nslots': len(v['slots']),
                      'slots': [hex(base + r) for r in v['slots']],
                      'sizes': [fsize(r) for r in v['slots']]} for v in lst]
    json.dump(res, open(out, 'w'), indent=0)
    print('classes with vtables', len(res), file=sys.stderr)
    # 集計: 名前空間トップ2
    ns = collections.Counter()
    for k in res:
        parts = k.split('@')
        ns['::'.join(parts[0].split('::')[:2])] += 1
    for k, v in ns.most_common(15):
        print('  ns %-40s %d' % (k, v), file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
