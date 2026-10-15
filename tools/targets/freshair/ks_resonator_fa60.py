#!/usr/bin/env python3
"""KH Resonator process (HeartCore 0x180743390) の SC 側対応を機械語で探す (FA-60 / #4978)。

3 つの照合を行い、表形式で出す。
  (a) SC ResonatorDsp vtable の各 slot と KH process の M 列比 (ks_identity.py の norm を使う)
  (b) SC 全関数 (.pdata・300〜3000 B) を KH process と M 列比で総当たり (上位 10)
  (c) SC の Resonator 関連 vtable と、各 SC 候補 slot を参照する関数 (RIP 相対 lea/mov の参照元)
usage: ks_resonator_fa60.py <HeartCore.core_64> <SlateCore.core_64> [out.json]
"""
import sys, json, difflib, struct
import capstone
from ks_identity import Pe, vtables
import os, tempfile

KH_PROC = 0x180743390
KH_VT = 0x181f03e78  # KH ResonatorDsp vtable (rtti_walk 由来・参照用)
SC_VT_NAME = '.?AVResonatorDsp@resonator@@'


def main():
    kh_path, sc_path = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    kh, sc = Pe(kh_path), Pe(sc_path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    td = tempfile.mkdtemp()
    sv = vtables(sc_path, os.path.join(td, 's.json'))
    kv = vtables(kh_path, os.path.join(td, 'k.json'))
    ks = kv[SC_VT_NAME][0]['slots']
    ss = sv[SC_VT_NAME][0]['slots']
    kins, _ = kh.disasm(KH_PROC)
    kn = kh.norm(kins)
    kconst = consts(md, kh, KH_PROC)
    res = {'kh_proc': hex(KH_PROC), 'kh_ninsn': len(kins), 'kh_bytes': sum(i.size for i in kins), 'slots': [], 'scan': [], 'refs': {}}

    print('(a) SC ResonatorDsp vtable 対 KH process 0x%x (%d insn, %d B)' % (KH_PROC, len(kins), res['kh_bytes']))
    for j, va in enumerate(ss):
        ins, _ = sc.disasm(int(va, 16))
        if len(ins) < 3:
            continue
        n = sc.norm(ins)
        rm = difflib.SequenceMatcher(None, kn[2], n[2], autojunk=False).ratio()
        row = {'sc_slot': j, 'sc_va': va, 'ninsn': len(ins), 'bytes': sum(i.size for i in ins), 'ratio_M': round(rm, 4),
               'shared_consts': len(kconst & consts(md, sc, int(va, 16)))}
        res['slots'].append(row)
        print('  slot %2d %s n=%4d B=%5d ratioM=%.4f shared_consts=%d' % (j, va, row['ninsn'], row['bytes'], rm, row['shared_consts']))

    print('(b) SC 全関数の総当たり (M 列比・上位 10)')
    scored = []
    for rva in sc.starts:
        size = sc.fn[rva] - rva
        if size < 300 or size > 3000:
            continue
        try:
            code = sc.rva_bytes(rva, size)
        except StopIteration:
            continue
        ins = list(sc.md.disasm(code, sc.base + rva))
        if not ins:
            continue
        m = sc.norm(ins)[2]
        sm = difflib.SequenceMatcher(None, kn[2], m, autojunk=False)
        if sm.real_quick_ratio() < 0.3 or sm.quick_ratio() < 0.3:
            continue
        scored.append((round(sm.ratio(), 4), sc.base + rva, len(ins), sum(i.size for i in ins)))
    scored.sort(reverse=True)
    for r, va, n, b in scored[:10]:
        print('  %.4f 0x%x n=%d B=%d' % (r, va, n, b))
        res['scan'].append({'ratio_M': r, 'va': hex(va), 'ninsn': n, 'bytes': b})

    print('(c) SC の Resonator vtable slot と参照元 (RIP 相対・即値)')
    watch = {int(s['sc_va'], 16): s['sc_va'] for s in res['slots'] if s['ratio_M'] >= 0.1}
    for name, lst in sv.items():
        if 'Resonator' in name:
            for vt in lst:
                for s_va in vt['slots']:
                    watch.setdefault(int(s_va, 16), s_va)
    refs = {}
    for rva in sc.starts:
        size = sc.fn[rva] - rva
        if size > 20000:
            continue
        try:
            code = sc.rva_bytes(rva, size)
        except StopIteration:
            continue
        for ins in md.disasm(code, sc.base + rva):
            for op in ins.operands:
                t = None
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                elif op.type == capstone.x86.X86_OP_IMM:
                    t = op.imm
                if t in watch:
                    refs.setdefault(watch[t], []).append(hex(sc.base + rva))
    for k, v in refs.items():
        print('  %s: %d 件 %s' % (k, len(v), ' '.join(sorted(set(v))[:8])))
    res['refs'] = {k: sorted(set(v)) for k, v in refs.items()}
    print('(d) KH process の呼出先と SC 側の r 列比較 (数値を潰した比較・上位 5)')
    cal = sorted({int(i.op_str, 16) for i in kins if i.mnemonic == 'call' and i.op_str.startswith('0x')})
    res['callees'] = []
    for t in cal:
        cins, _ = kh.disasm(t)
        cr = kh.norm(cins)[1]
        print('  KH callee 0x%x insn=%d' % (t, len(cins)))
        best = []
        for rva in sc.starts:
            size = sc.fn[rva] - rva
            if size < 100 or size > 3000:
                continue
            try:
                code = sc.rva_bytes(rva, size)
            except StopIteration:
                continue
            x = list(md.disasm(code, sc.base + rva))
            if not x:
                continue
            sm = difflib.SequenceMatcher(None, cr, sc.norm(x)[1], autojunk=False)
            if sm.real_quick_ratio() < 0.5 or sm.quick_ratio() < 0.5:
                continue
            best.append((round(sm.ratio(), 4), hex(sc.base + rva), len(x)))
        best.sort(reverse=True)
        for r, va, n in best[:5]:
            print('    %.4f %s n=%d' % (r, va, n))
        res['callees'].append({'kh': hex(t), 'top': [{'r': r, 'va': va, 'ninsn': n} for r, va, n in best[:5]]})
    if out:
        json.dump(res, open(out, 'w'), indent=1)


def consts(md, pe, va):
    rva = va - pe.base
    size = pe.fn[rva] - rva if rva in pe.fn else 4096
    vals = set()
    for ins in md.disasm(pe.rva_bytes(rva, size), va):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                try:
                    vals.add(pe.rva_bytes(t - pe.base, 8))
                except StopIteration:
                    pass
            if op.type == capstone.x86.X86_OP_IMM:
                vals.add(struct.pack('<q', op.imm))
    return vals


if __name__ == '__main__':
    main()
