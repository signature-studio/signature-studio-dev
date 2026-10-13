#!/usr/bin/env python3
"""SlateCore 側 Fresh Air DSP closure (FreshAirDsp + Gain/Filter/Compressor の全 vtable slot からの direct-call 到達集合) の
うち、HeartCore に E 正規化で完全一致する関数がどれだけあるか (#52)。closure.py と同じく間接 call は辿らない (下限)。
usage: ks_closure_share.py <HeartCore.core_64> <SlateCore.core_64> <out.json>
"""
import sys, os, re, json, hashlib, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe, vtables

ROOTS = ['.?AVFreshAirDsp@freshair@@', '.?AVGainDsp@gain@@', '.?AVFilterDsp@filter@@', '.?AVCompressorDsp@compressor@@']
STOP = 0x1803ded20  # freshair REPORT §3.2: vector 再配置


def h(pe, va):
    ins, _ = pe.disasm(va)
    return hashlib.sha1('\n'.join(pe.norm(ins)[0]).encode()).hexdigest(), ins


def rip_data(pe, va, n=16):
    """関数内の [rip+disp] 参照先のうち .rdata (定数) 側だけを (.data のグローバルは別バイナリで内容が違って当然なので除外)出現順に n バイトずつ読む。"""
    ins, _ = pe.disasm(va)
    out = []
    for i in ins:
        m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', i.op_str)
        if m:
            t = i.address + i.size + (int(m.group(2), 16) * (1 if m.group(1) == '+' else -1))
            rva = t - pe.base
            sec = next((x for x in pe.pe.sections if x.VirtualAddress <= rva < x.VirtualAddress + x.Misc_VirtualSize), None)
            if sec is not None and sec.Name.rstrip(b'\0') == b'.rdata':
                try:
                    out.append(pe.rva_bytes(rva, n))
                except StopIteration:
                    out.append(b'?')
    return out


def closure(pe, roots):
    seen, todo = {}, list(roots)
    while todo:
        va = todo.pop()
        if va in seen or va == STOP:
            continue
        rva = va - pe.base
        if rva not in pe.fn or not (pe.t_lo <= rva < pe.t_hi):
            continue
        hh, ins = h(pe, va)
        seen[va] = (hh, len(ins), sum(i.size for i in ins))
        for i in ins:
            if i.mnemonic in ('call', 'jmp') and re.fullmatch(r'0x[0-9a-f]+', i.op_str):
                t = int(i.op_str, 16)
                if t != va and not (va <= t < va + (pe.fn[rva] - rva)):
                    todo.append(t)
    return seen


def main(kp, sp, out):
    kh, sc = Pe(kp), Pe(sp)
    td = tempfile.mkdtemp()
    sv = vtables(sp, os.path.join(td, 's.json'))
    kh_hashes, kh_by_hash = set(), {}
    for rva in kh.starts:
        if kh.t_lo <= rva < kh.t_hi:
            hh = h(kh, kh.base + rva)[0]
            kh_hashes.add(hh)
            kh_by_hash.setdefault(hh, []).append(hex(kh.base + rva))
    res = {}
    allc = {}
    for r in ROOTS:
        roots = [int(x, 16) for x in sv[r][0]['slots']]
        c = closure(sc, roots)
        allc.update(c)
        shared = [v for v in c.values() if v[0] in kh_hashes]
        res[r] = {'funcs': len(c), 'bytes': sum(v[2] for v in c.values()), 'shared_funcs': len(shared), 'shared_bytes': sum(v[2] for v in shared)}
    shared = {va: v for va, v in allc.items() if v[0] in kh_hashes}
    res['union'] = {'funcs': len(allc), 'bytes': sum(v[2] for v in allc.values()), 'shared_funcs': len(shared), 'shared_bytes': sum(v[2] for v in shared.values()),
                    'unshared_funcs_ge12insn': sum(1 for v in allc.values() if v[0] not in kh_hashes and v[1] >= 12),
                    'shared_map_sc_to_kh': {hex(a): kh_by_hash[v[0]] for a, v in sorted(shared.items())}}
    same, diff, nodata = [], [], 0
    for a, v in sorted(shared.items()):
        kva = int(kh_by_hash[v[0]][0], 16)
        da, db = rip_data(sc, a), rip_data(kh, kva)
        if not da:
            nodata += 1
        elif da == db:
            same.append(hex(a))
        else:
            diff.append(hex(a))
    res['union']['rdata_check'] = {'no_rip_data': nodata, 'rdata_same': len(same), 'rdata_differ': len(diff), 'differ_vas': diff}
    json.dump(res, open(out, 'w'), indent=1)
    print('rdata_check', res['union']['rdata_check'])
    for k, v in res.items():
        print(k, {a: b for a, b in v.items() if a != 'shared_map_sc_to_kh'})


if __name__ == '__main__':
    main(*sys.argv[1:4])
