#!/usr/bin/env python3
"""MX-63 (#5908): E 証拠 site の転送先 G が、どの pdata 関数のどこに入るかを数える。

G が pdata 始点でなく、かつ pdata 関数の途中 (mid) なら、G の入口 livein は関数の入口値ではない。
判定: G が pdata 始点 / 他関数の内部 (命令境界か) / pdata の外。
usage: mx63_g_containment.py <pe> <split.json> <out.json>
"""
import bisect
import json
import sys

import capstone
import pefile


def main(pe_path, split_p, out_p):
    d = json.load(open(split_p))
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st, e = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4))
        if st and e > st and t_lo <= st < t_hi:
            funcs[st] = e
    begins = sorted(funcs)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def containing(t):
        j = bisect.bisect_right(begins, t) - 1
        if j < 0:
            return None
        s = begins[j]
        return s if t < funcs[s] else None

    def is_boundary(fs, t):
        code = data[text.PointerToRawData + (fs - t_lo):text.PointerToRawData + (funcs[fs] - t_lo)]
        return any(i.address - base == t for i in md.disasm(code, fs + base))

    out = {'sites': [], 'counts': {}}
    for f, v in d['F'].items():
        for s in v['sites']:
            if s['cat'] != 'E' or not s['G_livein45']:
                continue
            t = int(s['G'], 16)
            if not (t_lo <= t < t_hi):
                k = 'outside_text'
                c = None
            elif t in funcs:
                k, c = 'pdata_begin', None
            else:
                c = containing(t)
                if c is None:
                    k = 'no_pdata_range'
                elif is_boundary(c, t):
                    k = 'mid_function_insn_boundary'
                else:
                    k = 'mid_function_not_boundary'
            out['counts'][k] = out['counts'].get(k, 0) + 1
            out['sites'].append({'F': f, 'site': s['site'], 'G': s['G'], 'kind': s['kind'],
                                 'G_livein45': s['G_livein45'], 'class': k,
                                 'G_fn': None if c is None else hex(c)})
    json.dump(out, open(out_p, 'w'), indent=1)
    print('MX-63 G containment (E sites with livein45): %s' % out['counts'])
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
