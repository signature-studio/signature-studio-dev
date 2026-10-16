#!/usr/bin/env python3
"""MX-63 (#5908): 非境界 G について、capstone の線形復号が G の手前で止まるかを数える。

mx63_g_containment.py の capstone 復号は md.disasm() を関数先頭から最後まで回す。
復号できないバイトに当たると capstone はそこで出力を打ち切る。その停止位置 (cs_stop) が G より
手前なら、G が命令境界に乗らないのは復号の停止による見かけ上の結果と読める。
  - cs_stop_before_G: 停止位置 < G (capstone の線形復号は G の手前で止まる)
  - cs_stop_after_G:  停止位置 >= G (G の手前までは復号できている)
  - cs_full:          関数末尾まで停止せず復号できた
usage: mx63_g_cs_stop.py <pe> <contain.json> <out.json>
"""
import json
import sys

import capstone
import pefile


def main(pe_path, contain_p, out_p):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = text.VirtualAddress
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st = int.from_bytes(praw[i:i + 4], 'little')
        e = int.from_bytes(praw[i + 4:i + 8], 'little')
        if st and e > st:
            funcs[st] = e
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    d = json.load(open(contain_p))
    rows = []
    for s in d['sites']:
        if s['class'] != 'mid_function_not_boundary':
            continue
        g, fs = int(s['G'], 16), int(s['G_fn'], 16)
        fe = funcs[fs]
        code = data[text.PointerToRawData + (fs - t_lo):text.PointerToRawData + (fe - t_lo)]
        last_end = fs
        for i in md.disasm(code, fs + base):
            last_end = i.address - base + i.size
        if last_end >= fe:
            k = 'cs_full'
        elif last_end <= g:
            k = 'cs_stop_before_G'
        else:
            k = 'cs_stop_after_G'
        fwd = 'fwd_bad'
        gcode = data[text.PointerToRawData + (g - t_lo):text.PointerToRawData + (fe - t_lo)]
        for i in md.disasm(gcode, g + base):
            if i.mnemonic == 'ret':
                fwd = 'fwd_ret'
                break
        rows.append({'site': s['site'], 'G': hex(g), 'G_fn': hex(fs), 'fn_end': hex(fe),
                     'cs_stop': hex(last_end), 'class': k, 'from_G': fwd})
    summ = {'n': len(rows)}
    for r in rows:
        summ[r['class']] = summ.get(r['class'], 0) + 1
        summ[r['from_G']] = summ.get(r['from_G'], 0) + 1
    print('MX-63 capstone stop: %s' % json.dumps(summ))
    json.dump({'summary': summ, 'rows': rows}, open(out_p, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
