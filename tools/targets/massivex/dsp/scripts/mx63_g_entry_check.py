#!/usr/bin/env python3
"""MX-63 (#5908): E 証拠 site の転送先 G が関数入口らしいかを確かめる (REPORT §2 の定義: 入口 = 直接 call/jmp 先)。

G の直前バイトが int3 (0xCC) / nop (0x90) の詰め物なら、G は関数の先頭とみなせる。
G の入口 livein xmm4/5 は G から直接復号して求めた値 (mx63_u3e_split.py と同じ解析)。
usage: mx63_g_entry_check.py <pe> <split.json> <out.json>
"""
import json
import sys

import pefile


def main(pe_path, split_p, out_p):
    d = json.load(open(split_p))
    pe = pefile.PE(pe_path, fast_load=True)
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    data = open(pe_path, 'rb').read()
    raw = text.PointerToRawData

    def byte_at(va):
        return data[raw + (va - t_lo)]

    out = {'sites': [], 'counts': {}}
    for f, v in d['F'].items():
        for s in v['sites']:
            if s['cat'] != 'E' or not s['G_livein45']:
                continue
            t = int(s['G'], 16)
            if not (t_lo <= t < t_hi):
                k = 'outside_text'
            else:
                prev = byte_at(t - 1)
                k = 'pad_before_cc' if prev == 0xCC else ('pad_before_nop' if prev == 0x90 else 'no_pad')
            out['counts'][k] = out['counts'].get(k, 0) + 1
            out['sites'].append({'F': f, 'site': s['site'], 'G': s['G'], 'G_livein45': s['G_livein45'], 'prev_pad': k})
    json.dump(out, open(out_p, 'w'), indent=1)
    print('MX-63 G entry check: %s' % out['counts'])
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
