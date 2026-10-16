#!/usr/bin/env python3
"""MX-63 (#5908): 非境界とされた E 転送先 G を binutils objdump で独立に検算する。

mx63_g_containment.py は capstone の線形復号で G の命令境界を判定した (35 件が非境界)。
本スクリプトは objdump (binutils) の線形復号で同じ 35 件を見直す。
  - 転送 site: objdump でも call/jmp で、飛び先が G と一致するか
  - G: G_fn の線形復号 (objdump) の命令境界か
  - G: G_fn の先頭から直接の制御フロー (fallthrough・jcc/jmp 直接先) で G に届くか
    (間接 jmp は追えない。含む関数数を別に数える)
  - G から直接復号したとき、関数先頭の線形境界へ何バイトで再同期するか (参考値)
usage: mx63_g_objdump_check.py <pe> <contain.json> <out.json>
"""
import bisect
import json
import re
import subprocess
import sys

import pefile

IMAGE_BASE_FALLBACK = 0x180000000


def main(pe_path, contain_p, out_p):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase or IMAGE_BASE_FALLBACK
    data = open(pe_path, 'rb').read()
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st = int.from_bytes(praw[i:i + 4], 'little')
        e = int.from_bytes(praw[i + 4:i + 8], 'little')
        if st and e > st:
            funcs[st] = e
    begins = sorted(funcs)
    cache = {}

    def dis(lo, hi):
        if (lo, hi) in cache:
            return cache[(lo, hi)]
        r = subprocess.run(['objdump', '-d', '-M', 'intel', '--no-show-raw-insn',
                            '--start-address=0x%x' % (lo + base),
                            '--stop-address=0x%x' % (hi + base), pe_path],
                           capture_output=True, text=True).stdout
        ins = {}
        for line in r.splitlines():
            m = re.match(r'\s*([0-9a-f]+):\t(.*)$', line)
            if m:
                ins[int(m.group(1), 16) - base] = m.group(2).strip()
        cache[(lo, hi)] = ins
        return ins

    def lengths(ins):
        ks = sorted(ins)
        return {k: (ks[i + 1] - k if i + 1 < len(ks) else 1) for i, k in enumerate(ks)}

    def flow(ins, lens, start, end):
        seen, stack, indirect = set(), [start], 0
        while stack:
            a = stack.pop()
            if a in seen or a not in ins or not (start <= a < end):
                continue
            seen.add(a)
            t = ins[a]
            mn = t.split()[0] if t else ''
            m = re.match(r'(j\w+|call)\s+0x([0-9a-f]+)\s*$', t)
            nxt = a + lens.get(a, 1)
            if mn == 'jmp' and m:
                stack.append(int(m.group(2), 16) - base)
            elif mn == 'jmp':
                indirect += 1
            elif mn.startswith('j') and m:
                stack.append(int(m.group(2), 16) - base)
                stack.append(nxt)
            elif mn in ('ret', 'ud2', 'int3'):
                pass
            else:
                stack.append(nxt)
        return seen, indirect

    def site_target(site):
        out = dis(site, site + 16)
        t = out.get(site, '')
        m = re.match(r'(call|jmp)\s+0x([0-9a-f]+)', t)
        return (int(m.group(2), 16) - base) if m else None, t

    d = json.load(open(contain_p))
    rows = []
    for s in d['sites']:
        if s['class'] != 'mid_function_not_boundary':
            continue
        site, g, fs = int(s['site'], 16), int(s['G'], 16), int(s['G_fn'], 16)
        fe = funcs[fs]
        tgt, site_txt = site_target(site)
        ins = dis(fs, fe + 0x40)
        lens = lengths(ins)
        seen, ind = flow(ins, lens, fs, fe)
        g_bound = g in ins
        g_reach = g in seen
        lin = sorted(k for k in ins if k < fe)
        resync = None
        if not g_bound:
            from_g = dis(g, g + 0x80)
            for a in sorted(from_g)[:40]:
                if a in ins:
                    resync = a
                    break
        rows.append({'site': s['site'], 'G': hex(g), 'G_fn': hex(fs), 'site_insn': site_txt,
                     'site_target_is_G': tgt == g, 'G_linear_boundary': g_bound,
                     'G_reachable_direct_flow': g_reach, 'indirect_jmp_in_fn': ind,
                     'G_resync_to_linear': None if resync is None else hex(resync),
                     'G_insn': ins.get(g, ''), '_n': len(lin)})

    summ = {'n': len(rows),
            'site_insn_is_call_or_jmp_to_G': sum(r['site_target_is_G'] for r in rows),
            'G_linear_boundary_objdump': sum(r['G_linear_boundary'] for r in rows),
            'G_reachable_direct_flow': sum(r['G_reachable_direct_flow'] for r in rows),
            'fn_with_indirect_jmp': sum(1 for r in rows if r['indirect_jmp_in_fn'] > 0),
            'nonboundary_resync_within_40_insn': sum(1 for r in rows
                                                     if not r['G_linear_boundary']
                                                     and r['G_resync_to_linear'])}
    for r in rows:
        r.pop('_n', None)
    print('MX-63 objdump check: %s' % json.dumps(summ))
    json.dump({'summary': summ, 'rows': rows}, open(out_p, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
