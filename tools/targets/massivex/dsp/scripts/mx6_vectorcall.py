#!/usr/bin/env python3
"""MX-6 (#1123) U3: VST3 closure の vectorcall 独自規約の静的検出 (独立再計算・NC 付き)。

判定根拠: Win64 ABI の引数レジスタは xmm0〜xmm3 のみ。xmm4 / xmm5 を、入口から
どの経路でも書かれる前に読む関数は、呼出側が xmm4/5 に値を載せる規約 (vectorcall の
HVA / __m128 の 5 番目以降の引数) を受ける。
  - 本体: 入口からの CFG 上で must-def (全経路で書かれている集合) を取り、書かれていない xmm_k の読みを検出。
    間接 jmp は MSVC の相対 int32 テーブル形 (lea 基底 + cmp 境界) を解決する。解決できない間接 jmp は
    全命令への後続と見なす (過大近似。livein の偽陽性側にだけ誤差が出る)。
  - 独立再計算: CFG を使わない線形逆アセンブルで xmm4/5 を参照する関数数 (上限。livein ⊆ anyref が必須)
  - 限界: xmm0〜3 の livein は Win64 と区別できないため判定しない (ambiguous として件数のみ出す)。

usage: mx6_vectorcall.py <pe> <roots_seeds.json> <roots_one.json> <out.json>
       mx6_vectorcall.py --selftest
"""
import bisect
import json
import re
import sys

import capstone
import pefile
from capstone import x86

XMM_RE = re.compile(r'^[xyz]mm(\d+)$')
XOR_IDIOM = {'pxor', 'vpxor', 'vpxord', 'vpxorq', 'xorps', 'xorpd', 'vxorps', 'vxorpd'}
VOLATILE = 0x3F  # xmm0-5: call で clobber される
MEM_RE = re.compile(r'\[(\w+) \+ (\w+)\*4(?: \+ (-?0x[0-9a-f]+|\d+))?\]')
LEA_RIP_RE = re.compile(r'\[rip ([+-]) 0x([0-9a-f]+)\]')
CMP_IMM_RE = re.compile(r'\w+, (0x[0-9a-f]+|\d+)')


def _regidx(md, rid):
    m = XMM_RE.match(md.reg_name(rid) or '')
    return int(m.group(1)) if m and int(m.group(1)) < 16 else None


def effects(md, ins):
    """(read_mask, write_mask) over xmm0-15。同一レジスタの XOR idiom は読まない扱い。"""
    rd, wr = ins.regs_access()
    rmask = wmask = 0
    regs = [op.reg for op in ins.operands if op.type == x86.X86_OP_REG]
    idiom = ins.mnemonic in XOR_IDIOM and len(regs) >= 2 and len(set(regs)) == 1
    for r in rd:
        k = _regidx(md, r)
        if k is not None and not idiom:
            rmask |= 1 << k
    for r in wr:
        k = _regidx(md, r)
        if k is not None:
            wmask |= 1 << k
    return rmask, wmask


def _dword_alias(reg):
    if re.fullmatch(r'r\d+', reg):
        return reg + 'd'
    return 'e' + reg[1:]


def jt_targets(insns, k, read_abs):
    """`jmp reg` の相対 int32 テーブルを解決する。形: lea B,[rip+X] / cmp R,N / ja / movsxd|mov R,dword[B+I*4+d] / add R,B / jmp R。
    解決できなければ None。"""
    ins = insns[k]
    if not re.fullmatch(r'[a-z0-9]+', ins.op_str):
        return None
    reg = ins.op_str
    j = next((q for q in range(k - 1, max(0, k - 8), -1)
              if insns[q].mnemonic == 'add' and insns[q].op_str.startswith(reg + ', ')), None)
    if j is None:
        return None
    base = insns[j].op_str.split(', ')[1]
    dests = (reg, _dword_alias(reg))
    q = next((q for q in range(j - 1, max(0, j - 4), -1)
              if insns[q].mnemonic in ('movsxd', 'mov')
              and any(insns[q].op_str.startswith(d + ', dword ptr [') for d in dests)), None)
    if q is None:
        return None
    m = MEM_RE.search(insns[q].op_str)
    if not m or m.group(1) != base:
        return None
    disp = int(m.group(3), 0) if m.group(3) else 0
    bval = None
    for r in range(q - 1, -1, -1):
        w = insns[r]
        if w.op_str.startswith(base + ', '):
            if w.mnemonic == 'lea' and '[rip' in w.op_str:
                mm = LEA_RIP_RE.search(w.op_str)
                if mm:
                    d = int(mm.group(2), 16)
                    bval = w.address + w.size + (d if mm.group(1) == '+' else -d)
            break
    if bval is None:
        return None
    cmpn = None
    for r in range(q - 1, max(0, q - 12), -1):
        if insns[r].mnemonic == 'cmp':
            mc = CMP_IMM_RE.fullmatch(insns[r].op_str)
            if mc:
                cmpn = int(mc.group(1), 0)
            break
    if cmpn is None or cmpn > 255:
        return None
    tva = bval + disp
    raw = read_abs(tva, 4 * (cmpn + 1))
    if raw is None or len(raw) < 4 * (cmpn + 1):
        return None
    return [tva + int.from_bytes(raw[4 * i:4 * i + 4], 'little', signed=True) for i in range(cmpn + 1)]


def analyze(md, code, va, end_va, read_abs):
    insns = list(md.disasm(code, va))
    n = len(insns)
    if n == 0:
        return None
    idx = {i.address: k for k, i in enumerate(insns)}
    succ = [[] for _ in range(n)]
    unknown = False
    jt_resolved = 0
    eff = []
    for k, ins in enumerate(insns):
        rd, wr = effects(md, ins)
        is_call = bool(ins.group(x86.X86_GRP_CALL))
        if is_call:
            wr |= VOLATILE
        eff.append((rd, wr, is_call))
        if ins.group(x86.X86_GRP_RET) or ins.mnemonic in ('int3', 'ud2'):
            continue
        if ins.group(x86.X86_GRP_JUMP):
            if re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
                t = int(ins.op_str, 16)
                if t in idx:
                    succ[k].append(idx[t])
            else:
                tg = jt_targets(insns, k, read_abs)
                if tg is None:
                    unknown = True
                    succ[k] = list(range(n))
                else:
                    jt_resolved += 1
                    succ[k] = [idx[t] for t in tg if t in idx]
            if ins.mnemonic != 'jmp' and k + 1 < n:
                succ[k].append(k + 1)
            continue
        if k + 1 < n:
            succ[k].append(k + 1)
    # must-def (全経路で書かれている集合): 書かれる前の読みを検出
    must = [None] * n
    must[0] = 0
    work = [0]
    while work:
        k = work.pop()
        out = must[k] | eff[k][1]
        for s in succ[k]:
            new = out if must[s] is None else must[s] & out
            if new != must[s]:
                must[s] = new
                work.append(s)
    livein = 0
    live_at = []
    for k in range(n):
        if must[k] is not None:
            hit = eff[k][0] & ~must[k] & 0x30
            livein |= eff[k][0] & ~must[k] & 0xFFFF
            if hit:
                live_at.append(insns[k].address)
    # may-def (いずれかの経路で書かれた集合・call の clobber は除く): 呼出側の引数準備
    may = [None] * n
    may[0] = 0
    work = [0]
    while work:
        k = work.pop()
        rd, wr, is_call = eff[k]
        out = may[k] | (wr & ~VOLATILE if is_call else wr)
        for s in succ[k]:
            new = out | (may[s] or 0)
            if new != may[s]:
                may[s] = new
                work.append(s)
    call_args = []
    for k, ins in enumerate(insns):
        if eff[k][2] and may[k] is not None and re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
            m45 = may[k] & 0x30
            if m45:
                call_args.append((int(ins.op_str, 16), m45))
    anyref = 0
    for ins in insns:
        rd, wr = effects(md, ins)
        anyref |= (rd | wr) & 0x30
    return {'insns': n, 'livein': livein, 'live_at': live_at[:8], 'anyref': anyref,
            'unknown_flow': unknown, 'jt_resolved': jt_resolved, 'call_args': call_args}


def bits(m):
    return [k for k in range(16) if m >> k & 1]


def selftest():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    cases = [
        ('pos: movaps xmm0,xmm4; ret', bytes.fromhex('0f28c4c3'), True),
        ('pos: addps xmm5,xmm1; ret', bytes.fromhex('0f58e9c3'), True),
        ('neg: movaps xmm5,xmm1; addps xmm5,xmm1; ret', bytes.fromhex('0f28e90f58e9c3'), False),
        ('neg: pxor xmm4,xmm4 (idiom); movaps xmm0,xmm4; ret', bytes.fromhex('660fefe40f28c4c3'), False),
        ('pos: 分岐の一方だけ書く → 読みは maybe-undef', bytes.fromhex('4885c974030f28e00f28c4c3'), True),
    ]
    ok = True
    for name, code, want in cases:
        r = analyze(md, code, 0x1000, 0x1000 + len(code), lambda a, n: None)
        got = bool(r['livein'] & 0x30)
        ok &= got == want
        print('  %-52s livein=%s want=%s %s' % (name, bits(r['livein'] & 0x30), want,
                                                 'PASS' if got == want else 'FAIL'))
    print('selftest %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main(pe_path, seeds_p, one_p, out_p):
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
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st and t_lo <= st < t_hi:
            funcs[st] = (e, ui)
    begins = sorted(funcs)

    def off(r):
        return text.PointerToRawData + (r - t_lo)

    def fn_end(va):
        if va in funcs:
            return funcs[va][0]
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
    seeds = [int(x, 16) - base for x in json.load(open(seeds_p))['roots']]
    one = [int(x, 16) - base for x in json.load(open(one_p))['roots']]
    res = {}
    for label, roots in (('seeds', seeds), ('one_round', one)):
        rows = []
        for va in sorted(set(roots)):
            e = fn_end(va)
            code = data[off(va):off(va) + (e - va)]
            r = analyze(md, code, base + va, base + e, read_abs)
            if r is None:
                continue
            rows.append({'rva': hex(va), 'end': hex(e), 'pdata_begin': va in funcs,
                         'insns': r['insns'], 'livein45': bits(r['livein'] & 0x30),
                         'livein0_3': bits(r['livein'] & 0xF), 'anyref45': bits(r['anyref']),
                         'unknown_flow': r['unknown_flow'], 'jt_resolved': r['jt_resolved'],
                         'live_at45': [hex(a) for a in r['live_at']],
                         'call_args': [(hex(t), bits(m)) for t, m in r['call_args']]})
        vc = [x for x in rows if x['livein45']]
        res[label] = {
            'functions': len(rows), 'pdata_begin': sum(1 for x in rows if x['pdata_begin']),
            'insns': sum(x['insns'] for x in rows),
            'vectorcall_livein45': len(vc),
            'vectorcall_livein45_pdata_begin': sum(1 for x in vc if x['pdata_begin']),
            'livein45_non_pdata_begin_midentry': sum(1 for x in vc if not x['pdata_begin']),
            'vectorcall_pdata_begin_rvas': [x['rva'] for x in vc if x['pdata_begin']],
            'ambiguous_livein0_3_only': sum(1 for x in rows if not x['livein45'] and x['livein0_3']),
            'independent_anyref45_upper_bound': sum(1 for x in rows if x['anyref45']),
            'consistency_livein_subset_of_anyref': all(x['anyref45'] for x in vc),
            'unknown_flow_fns': sum(1 for x in rows if x['unknown_flow']),
            'jt_resolved_sites': sum(x['jt_resolved'] for x in rows),
            'calls_with_xmm45_defined_before': sum(len(x['call_args']) for x in rows),
            'rows': rows,
        }
    lin = {}
    for label, roots in (('seeds', seeds), ('one_round', one)):
        cnt = 0
        for va in set(roots):
            e = fn_end(va)
            cnt += any((rd | wr) & 0x30 for rd, wr in
                       (effects(md, i) for i in md.disasm(data[off(va):off(va) + (e - va)], base + va)))
        lin[label] = cnt
    res['linear_recount_anyref45'] = lin
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1)
    for label in ('seeds', 'one_round'):
        d = res[label]
        print('%-10s fn=%d (pdata begin %d) insns=%d | livein xmm4/5 pdata=%d (mid-entry %d) | '
              'xmm0-3 only(ambiguous)=%d | anyref upper=%d (linear %d) | consistency=%s | '
              'unknown_flow=%d jt_resolved=%d | xmm45 defined before call=%d'
              % (label, d['functions'], d['pdata_begin'], d['insns'],
                 d['vectorcall_livein45_pdata_begin'], d['livein45_non_pdata_begin_midentry'],
                 d['ambiguous_livein0_3_only'], d['independent_anyref45_upper_bound'], lin[label],
                 d['consistency_livein_subset_of_anyref'], d['unknown_flow_fns'],
                 d['jt_resolved_sites'], d['calls_with_xmm45_defined_before']))
        for x in d['vectorcall_pdata_begin_rvas']:
            print('   livein45 at pdata begin %s' % x)
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--selftest':
        sys.exit(selftest())
    sys.exit(main(*sys.argv[1:5]))
