#!/usr/bin/env python3
"""ott_extract.py — OTT (MSVC x64) の landing pad (funclet) 抽出 + 検証母数化 (CAB-227 ③).

MSVC x64 (OTT) と Delphi x64 (FLEngine) の構造差 (実測):
- OTT: landing pad = 独立 .pdata エントリ (funclet) で、UNW_FLAG_CHAININFO が親関数を指す。
  実測 2,096 件中 2,093 が親の「後ろ」に配置 (catch/finally funclet)、3 が前 (cold chunk)。
- FLEngine: landing pad は親関数範囲「内」の非到達コードで、scope table (handler data inline) が管理。

出力: fragments JSON (lift_pad.py と同じ形式) + 統計。
  python3 ott_extract.py --pe <OTT.dll> --json work/ott_fragments.json
"""
import argparse
import collections
import json
import struct

import capstone
import pefile

UP = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp',
      'r8d': 'r8', 'r9d': 'r9', 'r10d': 'r10', 'r11d': 'r11', 'r12d': 'r12', 'r13d': 'r13', 'r14d': 'r14', 'r15d': 'r15'}
GPR64 = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
CLOBBER = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--json', required=True)
    a = ap.parse_args()

    pe = pefile.PE(a.pe, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pdata = None
    for s in pe.sections:
        if s.Name.rstrip(b'\0').decode('latin1') == '.pdata':
            pdata = s.get_data()
    ents = [struct.unpack_from('<III', pdata, off) for off in range(0, len(pdata) // 12 * 12, 12)]
    by_begin = {b: (b, e, u) for b, e, u in ents if b}

    def unwind(ua):
        hdr = pe.get_data(ua, 4)
        if not hdr or len(hdr) < 4:
            return None
        return hdr[0] >> 3, hdr[1], hdr[2]

    handlers = collections.Counter()
    chain = []
    for b, e, u in ents:
        if not u:
            continue
        ua = u & ~1
        f = unwind(ua)
        if not f:
            continue
        if f[0] in (1, 2, 3):
            tail = (ua + 4 + f[2] * 2 + 3) & ~3
            d = pe.get_data(tail, 4)
            if d and len(d) == 4:
                handlers[base + struct.unpack('<I', d)[0]] += 1
        if f[0] & 4:
            tail = (ua + 4 + f[2] * 2 + 3) & ~3
            d = pe.get_data(tail, 4)
            ch = struct.unpack('<I', d)[0] if d and len(d) == 4 else None
            chain.append((b, e, ua, ch))

    # funclet (chaininfo 断片) = landing pad 候補
    text = None
    for s in pe.sections:
        if s.Name.rstrip(b'\0').decode('latin1') == '.text':
            text = (base + s.VirtualAddress, s.get_data())
    lo, tdata = text
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.detail = True
    from capstone import x86

    frags = []
    stats = collections.Counter()
    livein_c = collections.Counter()
    mn_all = collections.Counter()

    def hexva(v):
        return '0x%x' % v

    for b, e, ua, ch in chain:
        parent = by_begin.get(ch)
        bva, eva = base + b, base + e
        off = bva - lo
        code = tdata[off:eva - lo]
        insns = list(cs.disasm(code, bva))
        if not insns:
            stats['undecodable'] += 1
            continue
        defined = {'rsp'}
        li = set()
        for ins in insns:
            mn_all[ins.mnemonic] += 1
            if ins.mnemonic == 'call':
                defined |= CLOBBER
                continue
            try:
                rd, wr = ins.regs_access()
            except Exception:
                continue
            for r in rd:
                nm = UP.get(ins.reg_name(r), ins.reg_name(r))
                if nm in GPR64 and nm not in defined:
                    li.add(nm)
            for r in wr:
                nm = UP.get(ins.reg_name(r), ins.reg_name(r))
                if nm in GPR64:
                    defined.add(nm)
        livein_c[tuple(sorted(li))] += 1
        sites = []
        dcalls = []
        for ins in insns:
            grp = set(ins.groups)
            if (x86.X86_GRP_CALL in grp or x86.X86_GRP_JUMP in grp) and ins.operands and ins.operands[0].type != x86.X86_OP_IMM:
                op = ins.operands[0]
                d = {'va': hexva(ins.address), 'mn': ins.mnemonic}
                if op.type == x86.X86_OP_REG:
                    d['form'] = 'reg'
                    d['reg'] = ins.reg_name(op.reg)
                else:
                    mm = op.mem
                    bn = ins.reg_name(mm.base) if mm.base else None
                    if bn == 'rip':
                        d['form'] = 'rip'
                        d['slot'] = ins.address + ins.size + mm.disp
                    else:
                        d['form'] = 'mem'
                        d['base'] = bn
                        d['disp'] = mm.disp
                sites.append(d)
            if x86.X86_GRP_CALL in grp and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
                dcalls.append(ins.operands[0].imm)
        offs = []
        for ins in insns:
            for op in ins.operands:
                if op.type == x86.X86_OP_MEM:
                    bn = ins.reg_name(op.mem.base) if op.mem.base else None
                    if bn == 'rbp':
                        offs.append(op.mem.disp)
        frags.append({
            'kind': 'msvc_funclet', 'aux': None,
            'va_lo': bva, 'va_hi': eva, 'n_insns': len(insns),
            'bytes': code.hex(),
            'sites': sites, 'direct_calls': dcalls,
            'liveins': sorted(li),
            'mem_kinds': {},
            'frame_min': min(offs) if offs else None, 'frame_max': max(offs) if offs else None,
            'parent_rva': hexva(base + ch) if ch is not None else None,
            'insns': [{'va': hexva(x.address), 'mn': x.mnemonic, 'op': x.op_str, 'bytes': x.bytes.hex()} for x in insns],
        })
        stats['funclets'] += 1

    out = {'label': 'OTT', 'pe': a.pe, 'n_pdata': len(ents),
           'handlers': {hexva(k): v for k, v in handlers.most_common()},
           'n_chaininfo': len(chain), 'fragments': frags, 'stats': dict(stats),
           'liveins': {'%s' % (k,): v for k, v in livein_c.most_common()},
           'mnemonics': dict(mn_all.most_common(30))}
    json.dump(out, open(a.json, 'w'), indent=0)
    print('== OTT: pdata=%d handler-funcs=%d chaininfo(funclet)=%d fragments=%d' % (
        len(ents), sum(handlers.values()), len(chain), len(frags)))
    print('   handlers:', [(hexva(k), v) for k, v in handlers.most_common(6)])
    print('   funclet liveins top:', livein_c.most_common(6))
    print('   mnemonic top:', mn_all.most_common(12))


if __name__ == '__main__':
    main()
