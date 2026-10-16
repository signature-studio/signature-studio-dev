#!/usr/bin/env python3
"""MX-63 (#5908): 非境界 G の線形復号が信用できるかを調べる。

mx63_g_containment.py が「非境界」とした G (関数途中) について、G の関数内の線形復号
(objdump -d) に含まれる (bad) (デコード不能) の位置を数える。
  - bad_before_G: G より手前に (bad) がある = 線形復号は G の手前で信用できない
  - bad_free:     関数全体に (bad) が無い = 線形復号は関数全体で成立し、G は命令境界でない
usage: mx63_g_bad_bytes.py <pe> <contain.json> <out.json>
"""
import json
import re
import subprocess
import sys

import pefile


def main(pe_path, contain_p, out_p):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st = int.from_bytes(praw[i:i + 4], 'little')
        e = int.from_bytes(praw[i + 4:i + 8], 'little')
        if st and e > st:
            funcs[st] = e

    def dis(lo, hi):
        r = subprocess.run(['objdump', '-d', '-M', 'intel', '--no-show-raw-insn',
                            '--start-address=0x%x' % (lo + base),
                            '--stop-address=0x%x' % (hi + base), pe_path],
                           capture_output=True, text=True).stdout
        ins = {}
        for line in r.splitlines():
            m = re.match(r'\s*([0-9a-f]+):\t(.*)$', line)
            if m:
                ins[int(m.group(1), 16) - base] = m.group(2).strip()
        return ins

    d = json.load(open(contain_p))
    rows = []
    for s in d['sites']:
        if s['class'] != 'mid_function_not_boundary':
            continue
        g, fs = int(s['G'], 16), int(s['G_fn'], 16)
        ins = dis(fs, funcs[fs])
        bads = sorted(k for k, v in ins.items() if '(bad)' in v)
        rows.append({'site': s['site'], 'G': hex(g), 'G_fn': hex(fs),
                     'bad_before_G': any(b < g for b in bads),
                     'bad_in_fn': len(bads) > 0,
                     'G_objdump_boundary': g in ins})
    summ = {'n': len(rows),
            'bad_before_G': sum(r['bad_before_G'] for r in rows),
            'bad_free_fn': sum(not r['bad_in_fn'] for r in rows),
            'G_objdump_boundary': sum(r['G_objdump_boundary'] for r in rows)}
    print('MX-63 G bad-bytes: %s' % json.dumps(summ))
    json.dump({'summary': summ, 'rows': rows}, open(out_p, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
