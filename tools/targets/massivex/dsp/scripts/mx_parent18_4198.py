#!/usr/bin/env python3
"""MX-50 (#4198): 親 18 件 (CHAININFO 親が valid .pdata に完全一致で無い) の所在と形を分類する。

母集団は mx_unres_residual_4198.py と同じ (1 section に一意に解決・valid entry・CHAININFO)。
分類は 2 軸:
  - 親 (begin,end) が 2 本の .pdata のどちらかに完全一致で在るか (in_all_pdata)
  - 親 end が、同じ UNWIND_INFO を持つ子 entry の begin と一致するか (adjacent / end_in_text / end_other)

usage: mx_parent18_4198.py <pe>
"""
import sys, struct, collections
import pefile


def main(path):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    secs = pe.sections
    t = [s for s in secs if s.Characteristics & 0x20000000][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    pds = [s for s in secs if s.Name.rstrip(b'\0').decode() == '.pdata']
    all_pairs = set()
    for pd in pds:
        raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
        all_pairs |= set((b, e) for (b, e, u) in (struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)) if e > b and b)
    pd = pds[0]
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    valid_exact = set((b, e) for (b, e, u) in valid)
    valid_begins = set(b for (b, e, u) in valid)
    hits = lambda u: [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]
    fo = lambda s, r: s.PointerToRawData + (r - s.VirtualAddress)
    cls = collections.Counter()
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) != 1:
            continue
        ub = data[fo(hs[0], u): fo(hs[0], u) + 524]
        if not (ub[0] >> 3 & 4):
            continue
        cnt = ub[2]
        o = 4 + 2 * (cnt + (cnt & 1))
        pb, pe_, _ = struct.unpack_from('<III', ub, o)
        if (pb, pe_) in valid_exact:
            continue
        pin = 'in_all_pdata' if (pb, pe_) in all_pairs else 'not_in_pdata'
        if pe_ == b:
            end = 'end==child_begin'
        elif pe_ in valid_begins:
            end = 'end_in_valid_begins'
        elif t_lo <= pe_ <= t_hi:
            end = 'end_in_text_other'
        else:
            end = 'end_not_in_text'
        cls[pin + '/' + end] += 1
    print('pdata sections', len(pds), 'entries', len(ents), 'valid', len(valid))
    for k, n in sorted(cls.items()):
        print(k, n)
    print('total', sum(cls.values()))


if __name__ == '__main__':
    main(sys.argv[1])
