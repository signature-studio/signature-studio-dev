#!/usr/bin/env python3
"""gap_fragments.py — audit_icall (tools/icall, 読取専用再利用) の gap sweep 結果から
landing pad / thunk 断片を切り出し・分類する (CAB-227).

  python3 gap_fragments.py --pe <PE> --funcs <funcs.txt> --json out.json

断片の切り出し:
  1. recursive descent (audit_icall.Disasm.scan_function) の到達集合を求める
  2. gap 領域を gap_sweep と同じ規則で列挙 (clean decode できる塊のみ)
  3. gap site (間接 call/jmp) を含む塊を「断片」とする
  4. 断片を末尾 padding (nop/int3) でトリムし、さらに import thunk (`jmp [rip+iat]`) 単位で分割
分類 kind:
  dtor_pad     : 末尾が `call <reraise>` (0x411ea0 系, noreturn) — 実行検証対象
  other_pad    : 末尾がその他の noreturn 風 call
  dispatch_stub: `call <helper>; ...; jmp rax` 形 (Delphi except dispatch)
  import_thunk : `jmp [rip+IAT]` 単発
  other        : その他
断片ごとに live-in GPR / rbp フレーム参照 / 直接 callee / 間接 site を記録する。
"""
import argparse
import bisect
import collections
import json
import os
import struct
import sys

import capstone
import pefile

RERAISE_VA = 0x411EA0        # FLEngine: Delphi _Reraise 相当 (pad 末尾の noreturn call 先, 実測)

UP = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp',
      'r8d': 'r8', 'r9d': 'r9', 'r10d': 'r10', 'r11d': 'r11', 'r12d': 'r12', 'r13d': 'r13', 'r14d': 'r14', 'r15d': 'r15',
      'ax': 'rax', 'bx': 'rbx', 'cx': 'rcx', 'dx': 'rdx', 'si': 'rsi', 'di': 'rdi', 'bp': 'rbp', 'sp': 'rsp',
      'al': 'rax', 'bl': 'rbx', 'cl': 'rcx', 'dl': 'rdx', 'sil': 'rsi', 'dil': 'rdi', 'bpl': 'rbp', 'spl': 'rsp',
      'r8w': 'r8', 'r9w': 'r9', 'r10w': 'r10', 'r11w': 'r11', 'r12w': 'r12', 'r13w': 'r13', 'r14w': 'r14', 'r15w': 'r15',
      'r8b': 'r8', 'r9b': 'r9', 'r10b': 'r10', 'r11b': 'r11', 'r12b': 'r12', 'r13b': 'r13', 'r14b': 'r14', 'r15b': 'r15'}
GPR64 = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
CLOBBER = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}


def analyze_insns(insns, base, iat_lo, iat_hi):
    """断片 1 個の解析: live-in / frame slots / callees / sites / end kind."""
    defined = {'rsp'}
    li = set()
    frame_refs = []      # [rbp+disp] の読み書き (disp, size, 'r'/'w')
    sites = []           # 間接 call/jmp
    dcalls = []          # 直接 call 先
    mem_kinds = collections.Counter()
    last = None
    for ins in insns:
        if ins.mnemonic == 'call':
            defined |= CLOBBER
        try:
            rd, wr = ins.regs_access()
        except Exception:
            rd, wr = [], []
        for r in rd:
            nm = UP.get(ins.reg_name(r), ins.reg_name(r))
            if nm in GPR64 and nm not in defined:
                li.add(nm)
        for r in wr:
            nm = UP.get(ins.reg_name(r), ins.reg_name(r))
            if nm in GPR64:
                defined.add(nm)
        for op in ins.operands:
            if op.type != capstone.x86.X86_OP_MEM:
                continue
            m = op.mem
            bn = ins.reg_name(m.base) if m.base else None
            ix = ins.reg_name(m.index) if m.index else None
            if bn == 'rip' or ix == 'rip':
                mem_kinds['rip'] += 1
            elif bn == 'rbp' or ix == 'rbp':
                frame_refs.append({'off': m.disp, 'size': op.size, 'rw': 'r' if op in rd or True else 'w'})
                mem_kinds['rbp'] += 1
            elif bn == 'rsp':
                mem_kinds['rsp'] += 1
            elif bn is None:
                mem_kinds['abs'] += 1
            else:
                mem_kinds['reg'] += 1
        grp = set(ins.groups)
        is_call = capstone.x86.X86_GRP_CALL in grp
        is_jmp = capstone.x86.X86_GRP_JUMP in grp
        if (is_call or is_jmp) and ins.operands and ins.operands[0].type != capstone.x86.X86_OP_IMM:
            op = ins.operands[0]
            d = {}
            if op.type == capstone.x86.X86_OP_REG:
                d = {'form': 'reg', 'reg': ins.reg_name(op.reg)}
            else:
                mm = op.mem
                b = ins.reg_name(mm.base) if mm.base else None
                if b == 'rip':
                    slot = ins.address + ins.size + mm.disp
                    d = {'form': 'rip', 'slot': slot, 'iat': iat_lo <= slot < iat_hi}
                else:
                    d = {'form': 'mem', 'base': b, 'disp': mm.disp, 'index': ins.reg_name(mm.index) if mm.index else None}
            d.update({'va': ins.address, 'mn': ins.mnemonic, 'size': ins.size, 'bytes': ins.bytes.hex()})
            sites.append(d)
        if is_call and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            dcalls.append(ins.operands[0].imm)
        last = ins
    return {'liveins': sorted(li - {'rbp'}), 'frame_refs': frame_refs, 'sites': sites,
            'direct_calls': dcalls, 'mem_kinds': dict(mem_kinds), 'last': last}


def classify(insns, base, iat_lo, iat_hi, info):
    core = list(insns)
    while core and core[-1].mnemonic in ('nop', 'int3'):
        core.pop()
    if not core:
        return 'empty', None, core
    last = core[-1]
    sites = info['sites']
    if last.mnemonic == 'jmp' and last.operands and last.operands[0].type == capstone.x86.X86_OP_MEM:
        m = last.operands[0].mem
        if last.reg_name(m.base) == 'rip':
            slot = last.address + last.size + m.disp
            if iat_lo <= slot < iat_hi:
                return 'import_thunk', slot, core
    if last.mnemonic == 'jmp' and last.operands and last.operands[0].type == capstone.x86.X86_OP_IMM:
        return 'relay_thunk', last.operands[0].imm, core
    if last.mnemonic == 'jmp' and last.operands and last.operands[0].type == capstone.x86.X86_OP_REG:
        # call helper; ...; jmp rax 形?
        dc = info['direct_calls']
        if dc:
            return 'dispatch_stub', dc[-1], core
        return 'other', None, core
    if last.mnemonic == 'call' and last.operands[0].type == capstone.x86.X86_OP_IMM:
        t = last.operands[0].imm
        if t == RERAISE_VA:
            return 'dtor_pad', t, core
        return 'other_pad', t, core
    return 'other', None, core


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--funcs', required=True)
    ap.add_argument('--max-fn-size', type=int, default=0x40000)
    ap.add_argument('--json', required=True)
    ap.add_argument('--label', default='fle')
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    import audit_icall as A

    img = A.Image(a.pe)
    fns = sorted(set(int(t, 16) for t in open(a.funcs).read().split()))
    img.set_extra_starts(fns)
    dis = A.Disasm(img)
    sites = {}
    ninsn = 0
    for f in fns:
        rg = img.func_range(f)
        if not rg:
            continue
        fs, fe = rg
        if fe - fs > a.max_fn_size:
            fe = fs + a.max_fn_size
        seen = dis.scan_function(fs, fe, sites)
        ninsn += len(seen)
        dis.gap_sweep(fs, fe, seen, sites)
    gap_sites = sorted(s.va for s in sites.values() if s.gap)
    site_by_va = {s.va: s for s in sites.values() if s.gap}

    # gap 領域の列挙 (block 単位)
    blocks = []
    for f in fns:
        rg = img.func_range(f)
        if not rg:
            continue
        fs, fe = rg
        if fe - fs > a.max_fn_size:
            fe = fs + a.max_fn_size
        seen = dis.scan_function(fs, fe, {})
        cov = set()
        for va, ins in seen.items():
            for i in range(ins.size):
                cov.add(va + i)
        for lo, hi in dis.data_ranges:
            for x in range(max(lo, fs), min(hi, fe)):
                cov.add(x)
        va = fs
        while va < fe:
            if va in cov:
                va += 1
                continue
            g0 = va
            while va < fe and va not in cov:
                va += 1
            blocks.append((g0, va))
            va += 1

    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.detail = True

    pe = pefile.PE(a.pe, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    iat_lo = iat_hi = 0
    d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[12]
    dd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[13]
    lo = min([x for x in (d.VirtualAddress, dd.VirtualAddress) if x] or [0])
    hi = max([x + s for x, s in ((d.VirtualAddress, d.Size), (dd.VirtualAddress, dd.Size)) if x] or [0])
    if lo or hi:
        iat_lo, iat_hi = base + lo, base + hi

    frags = []
    for (g0, g1) in blocks:
        if not any(g0 <= s < g1 for s in gap_sites):
            continue
        insns = []
        p = g0
        ok = True
        while p < g1:
            m = None
            for x in cs.disasm(img.read(p, 16) or b'', p, 1):
                m = x
            if m is None or p + m.size > g1:
                ok = False
                break
            insns.append(m)
            p += m.size
        if not ok or not insns:
            continue
        # 断片分割: jmp/ret + (nop*) + int3 の並びを「島」の終端として切る
        # (dispatch stub / relay thunk / IAT thunk が 1 block に混在するため)
        segs = []
        cur = []
        idx = 0
        while idx < len(insns):
            ins = insns[idx]
            cur.append(ins)
            idx += 1
            if ins.mnemonic in ('jmp', 'ret'):
                j = idx
                while j < len(insns) and insns[j].mnemonic == 'nop':
                    j += 1
                if j < len(insns) and insns[j].mnemonic == 'int3':
                    while idx < j:
                        cur.append(insns[idx])
                        idx += 1
                    segs.append(cur)
                    cur = []
        if cur:
            segs.append(cur)
        for seg in segs:
            # 先頭の int3/nop を落とす (表示用の整列 padding)
            while seg and seg[0].mnemonic in ('int3', 'nop'):
                seg = seg[1:]
            if not seg:
                continue
            seg_lo = seg[0].address
            seg_hi = seg[-1].address + seg[-1].size
            if not any(seg_lo <= v < seg_hi for v in gap_sites):
                # site を含まない尾部 (padding 等) は捨てる
                continue
            info = analyze_insns(seg, base, iat_lo, iat_hi)
            kind, aux, core = classify(seg, base, iat_lo, iat_hi, info)
            has_site = [s for s in info['sites'] if s['va'] in site_by_va]
            if not has_site:
                continue
            lo_va = seg_lo
            hi_va = seg_hi
            # rbp フレーム参照の範囲
            offs = [fr['off'] for fr in info['frame_refs']]
            fr = {
                'kind': kind, 'aux': aux,
                'va_lo': lo_va, 'va_hi': hi_va, 'n_insns': len(seg),
                'bytes': b''.join(x.bytes for x in seg).hex(),
                'sites': info['sites'], 'direct_calls': info['direct_calls'],
                'liveins': info['liveins'], 'mem_kinds': info['mem_kinds'],
                'frame_min': min(offs) if offs else None, 'frame_max': max(offs) if offs else None,
                'insns': [{'va': x.address, 'mn': x.mnemonic, 'op': x.op_str, 'bytes': x.bytes.hex()} for x in seg],
            }
            fr['site_kinds'] = collections.Counter(s['mn'] + ':' + s.get('form', '') for s in has_site)
            frags.append(fr)

    frags.sort(key=lambda f: f['va_lo'])
    out = {'label': a.label, 'pe': a.pe, 'nfuncs': len(fns), 'ninsn': ninsn,
           'gap_sites': gap_sites, 'n_gap_sites': len(gap_sites), 'fragments': frags}
    kc = collections.Counter(f['kind'] for f in frags)
    out['kind_counts'] = dict(kc)
    json.dump(out, open(a.json, 'w'), indent=0)
    print('== %s: funcs=%d insn=%d gap_sites=%d fragments=%d kinds=%s' % (
        a.label, len(fns), ninsn, len(gap_sites), len(frags), dict(kc)))
    sk = collections.Counter()
    for f in frags:
        for s in f['sites']:
            sk['%s:%s' % (s['mn'], s['form'])] += 1
    print('   site forms:', dict(sk))


if __name__ == '__main__':
    main()
