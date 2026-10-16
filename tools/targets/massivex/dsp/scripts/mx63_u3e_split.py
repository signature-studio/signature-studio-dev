#!/usr/bin/env python3
"""MX-63 (#5908) U3e 切り分け: pdata 始点の候補 F ごとに、direct call/jmp の転送 site を分類する。

母集団: seeds ∪ one_round の pdata 始点 F のうち、F の入口 livein xmm4/5 = 0 (MX-54 #5019 の母集団)。
各 site s (F 内の direct call/jmp・関数外へ出る形) を次に分類する:
  D  F 内で xmm4/5 が (いずれかの経路で) 定義済み (may-def != 0): 転送値は入口値ではない
  C  前段に call がある (may-called): call は xmm0〜5 を clobber しうるため入口値と同一性を示せない
  E  定義なし・前段 call なし (may-def == 0 かつ not called): 転送値は F の入口値と同一 (証拠 E)
  G  G の入口 livein xmm4/5 が 0・または解析不能
G 入口 livein xmm4/5 != 0 かつ分類 E の site を持つ F を「入口値の転送証拠あり」とする。

usage: mx63_u3e_split.py <pe> <vectorcall.json> <out.json>
"""
import bisect
import json
import re
import sys

import capstone
import pefile
from capstone import x86

from mx6_vectorcall import VOLATILE, analyze, bits, effects


def main(pe_path, vc_p, out_p):
    vc = json.load(open(vc_p))
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

    def off(r):
        return text.PointerToRawData + (r - t_lo)

    def fn_end(va):
        if va in funcs:
            return funcs[va]
        j = bisect.bisect_right(begins, va)
        nxt = begins[j] if j < len(begins) else t_hi
        return min(nxt, va + 4096)

    def read_abs(va, n):
        try:
            return pe.get_data(va - base, n)
        except pefile.PEFormatError:
            return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def may_before(insns, succ, eff):
        n = len(insns)
        may = [None] * n
        called = [None] * n
        may[0] = 0
        called[0] = False
        work = [0]
        while work:
            k = work.pop()
            rd, wr, is_call = eff[k]
            out = may[k] | (wr & ~VOLATILE if is_call else wr)
            cout = called[k] or is_call
            for s in succ[k]:
                new = out | (may[s] or 0)
                cnew = cout or bool(called[s])
                if new != may[s] or cnew != called[s]:
                    may[s] = new
                    called[s] = cnew
                    work.append(s)
        return may, called

    def classify(F):
        e = fn_end(F)
        code = data[off(F):off(F) + (e - F)]
        r = analyze(md, code, base + F, base + e, read_abs)
        if r is None:
            return None
        if r['livein'] & 0x30:
            return {'skip': 'entry_livein45_nonzero'}
        insns, succ = r['cfg']
        eff = []
        for ins in insns:
            rd, wr = effects(md, ins)
            is_call = bool(ins.group(x86.X86_GRP_CALL))
            if is_call:
                wr |= VOLATILE
            eff.append((rd, wr, is_call))
        may, called = may_before(insns, succ, eff)
        sites = []
        for k, ins in enumerate(insns):
            if not (ins.group(x86.X86_GRP_CALL) or ins.group(x86.X86_GRP_JUMP)):
                continue
            if not re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
                continue
            t = int(ins.op_str, 16) - base
            if F <= t < e and not ins.group(x86.X86_GRP_CALL):
                continue
            if may[k] is None:
                continue
            if may[k] & 0x30:
                cat = 'D'
            elif called[k]:
                cat = 'C'
            else:
                cat = 'E'
            g = None
            if cat == 'E':
                if t_lo <= t < t_hi:
                    ge = fn_end(t)
                    gr = analyze(md, data[off(t):off(t) + (ge - t)], base + t, base + ge, read_abs) if ge > t else None
                    g = None if gr is None else gr['livein'] & 0x30
                if g is None:
                    cat = 'G'
                elif g == 0:
                    cat = 'G0'
                else:
                    cat = 'E'
            sites.append({'site': hex(ins.address - base), 'kind': ins.mnemonic, 'G': hex(t),
                          'cat': cat, 'G_livein45': None if g is None else bits(g)})
        return {'sites': sites}

    pops = {}
    for label in ('seeds', 'one_round'):
        for x in vc[label]['rows']:
            if x['pdata_begin']:
                pops.setdefault(int(x['rva'], 16), set()).add(label)
    out = {}
    for F in sorted(pops):
        if F not in funcs:
            continue
        res = classify(F)
        if res is None or 'skip' in res:
            continue
        out[hex(F)] = {'pop': sorted(pops[F]), 'sites': res['sites']}
    evidence = sorted(f for f, v in out.items()
                      if any(s['cat'] == 'E' and s['G_livein45'] for s in v['sites']))
    cats = {}
    for v in out.values():
        for s in v['sites']:
            cats[s['cat']] = cats.get(s['cat'], 0) + 1
    res = {'population_pdata_begin_livein45_zero': len(out), 'site_cat_counts': cats,
           'evidence_E_G_livein_nonzero_F': evidence, 'evidence_count': len(evidence), 'F': out}
    json.dump(res, open(out_p, 'w'), indent=1)
    print('MX-63 U3e split: population=%d evidence(E)=%d site_cat=%s' % (len(out), len(evidence), cats))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
