#!/usr/bin/env python3
"""MX-52 (#4989) 受入 2〜4 の感度測定 (U3d: merge 上位保持 / U3e: call 引数転送 / U3g: 非 vectorcall の scalar 落ち)。

既存の mx6_vectorcall.analyze (本体・must-def) は変えず、比較用の 2 変種を同じ CFG で計算する。
  base  : 既存規則 (部分書込 = 全幅の定義として must-def に入れる)
  u3d   : 部分書込 (merge: VEX 3 オペランド scalar/cvtsi2 の dest 上書き・movss/movsd の reg 宛先・movlps 等の下位だけ書く) は
          must-def に入れない。入口の xmm_k の上位が残るため、後続の読みを livein として数える。

usage: mx4989_probe.py <pe> <vectorcall.json> <out.json>
"""
import bisect
import json
import re
import sys

import capstone
import pefile
from capstone import x86

from capstone import x86

from mx6_vectorcall import analyze, bits, effects, _regidx
from mx33_xmm03 import follow, upper_flow_dst

PARTIAL = {'movss', 'movsd', 'movlps', 'movlpd', 'movhps', 'movhpd', 'movhlps', 'movlhps'}


def base_mnem(ins):
    m = ins.mnemonic
    return m[1:] if m.startswith('v') else m


def partial_dst(md, ins):
    """部分書込の宛先 xmm (なければ None)。merge (上位保持) の宛先のみ扱う。"""
    b = base_mnem(ins)
    ops = ins.operands
    if not ops or ops[0].type != x86.X86_OP_REG:
        return None
    d = _regidx(md, ops[0].reg)
    if d is None:
        return None
    nreg = sum(1 for o in ops if o.type != x86.X86_OP_IMM)
    if b in PARTIAL and nreg == 2 and ops[1].type == x86.X86_OP_REG:
        return d
    if nreg == 3 and (b.startswith('cvtsi2') or b.endswith(('ss', 'sd'))):
        return d
    if b.startswith('cvtsi2') and nreg == 2:
        return d
    return None


def must_partial_off(md, insns, succ, eff_w, eff_r):
    """must-def を計算。部分書込は must に入れない (宛先の上位保持を読みとして残す)。"""
    n = len(insns)
    must = [None] * n
    must[0] = 0
    work = [0]
    while work:
        k = work.pop()
        out = must[k] | eff_w[k]
        for s in succ[k]:
            new = out if must[s] is None else must[s] & out
            if new != must[s]:
                must[s] = new
                work.append(s)
    return must


def livein_u3d(md, r):
    insns, succ = r['cfg']
    n = len(insns)
    eff_r, eff_w = [], []
    part = []
    for ins in insns:
        rd, wr = effects(md, ins)
        eff_r.append(rd)
        pd = partial_dst(md, ins)
        part.append(pd)
        eff_w.append(wr & ~(1 << pd) if pd is not None else wr)
    must = must_partial_off(md, insns, succ, eff_w, eff_r)
    lin = 0
    where = []
    for k in range(n):
        if must[k] is not None:
            hit = eff_r[k] & ~must[k] & 0x30
            lin |= eff_r[k] & ~must[k] & 0xFFFF
            if hit:
                where.append((k, hit))
    evid = []
    for k, hit in where:
        for j in bits(hit):
            up = upper_flow_dst(md, insns[k], j)
            if up is None:
                evid.append((hex(insns[k].address), insns[k].mnemonic, insns[k].op_str, j, 'A', 'merge 形でない読み'))
                continue
            cls, why = follow(md, insns, succ, k, {up}, False, merge=True)
            evid.append((hex(insns[k].address), insns[k].mnemonic, insns[k].op_str, j, cls, why))
    return lin, evid


def u3e(md, data, base, text, read_abs, fn_end, rows, pdata_begins):
    """U3e (引数転送): 呼出側 F が xmm_k (k∈4,5) を入口から自分では読まず (livein 0)、direct call / jmp で
    xmm_k が未定義のまま G へ渡り、G の入口 livein に xmm_k が立つ F を数える。
    既存の livein は F の読みだけを見るため、この形は F の livein から落ちる。"""
    def off(r):
        return text.PointerToRawData + (r - text.VirtualAddress)

    gcache = {}

    def g_livein(t):
        if t not in gcache:
            e = fn_end(t)
            r = analyze(md, data[off(t):off(t) + (e - t)], base + t, base + e, read_abs) if e > t else None
            gcache[t] = None if r is None else r['livein'] & 0x30
        return gcache[t]

    out = []
    for x in rows:
        if x['livein45']:
            continue
        va = int(x['rva'], 16)
        e = int(x['end'], 16)
        code = data[off(va):off(va) + (e - va)]
        r = analyze(md, code, base + va, base + e, read_abs)
        if r is None:
            continue
        insns, succ = r['cfg']
        for k, ins in enumerate(insns):
            if not (ins.group(x86.X86_GRP_CALL) or ins.group(x86.X86_GRP_JUMP)):
                continue
            if not re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
                continue
            t = int(ins.op_str, 16) - base
            gl = g_livein(t)
            if gl and r['must'][k] is not None and gl & ~r['must'][k] & 0x30:
                out.append((x['rva'], hex(ins.address - base), ins.mnemonic, hex(t), bits(gl & ~r['must'][k] & 0x30)))
                break
    fns = sorted(set(o[0] for o in out))
    pdata_fns = [f for f in fns if int(f, 16) in pdata_begins]
    return {'livein45_zero_fn_with_direct_forward_to_livein_callee': len(fns),
            'of_which_pdata_begin': len(pdata_fns), 'pdata_begin_rvas': pdata_fns,
            'sites': out}


def main(pe_path, vc_p, out_p):
    vc = json.load(open(vc_p))
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]

    def off(r):
        return text.PointerToRawData + (r - text.VirtualAddress)

    def read_abs(va, n):
        try:
            return pe.get_data(va - base, n)
        except pefile.PEFormatError:
            return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t_hi = text.VirtualAddress + text.Misc_VirtualSize
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(praw) - 11, 12):
        st, e = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4))
        if st and e > st and text.VirtualAddress <= st < t_hi:
            funcs[st] = e
    begins = sorted(funcs)

    def fn_end(va):
        if va in funcs:
            return funcs[va]
        j = bisect.bisect_right(begins, va)
        nxt = begins[j] if j < len(begins) else t_hi
        return min(nxt, va + 4096)

    res = {}
    e3 = u3e(md, data, base, text, read_abs, fn_end, vc['seeds']['rows'] + vc['one_round']['rows'], set(funcs))
    res['u3e'] = e3
    for label in ('seeds', 'one_round'):
        rows = [x for x in vc[label]['rows'] if x['pdata_begin']]
        base_vc = [x['rva'] for x in rows if x['livein45']]
        new_vc, changed = [], []
        for x in rows:
            va, e = int(x['rva'], 16), int(x['end'], 16)
            code = data[off(va):off(va) + (e - va)]
            r = analyze(md, code, base + va, base + e, read_abs)
            if r is None:
                continue
            lin_u3d, where = livein_u3d(md, r)
            if lin_u3d & 0x30:
                new_vc.append(x['rva'])
                if not x['livein45']:
                    changed.append({'rva': x['rva'], 'reads': where[:8]})
        res[label] = {'pdata_begin': len(rows), 'livein45_base': len(base_vc),
                      'livein45_u3d': len(new_vc), 'newly_flagged_u3d': changed}
    json.dump(res, open(out_p, 'w'), indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
