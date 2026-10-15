#!/usr/bin/env python3
"""MX-54 (#5019) U3e: 呼出側 F が xmm4/5 を入口から読まず direct call/jmp で G へ未定義のまま渡すか。

入力: PE・seeds の JSON (mx6_vectorcall の seeds_x64c.json 形式)。
出力: JSON (件数・内訳・候補の RVA 一覧)。判定は mx6_vectorcall.analyze の CFG と effects を再利用する。

判定:
  F = pdata 始点かつ seeds の関数 (入口 livein xmm4/5 = 0 の母集団)。
  F の中で到達可能な direct call/jmp (即値, 関数外へ出る形) の site s について、
  s の直前で F 内に xmm4/5 の定義が無い (may-def が 0) とき、G = 転送先の入口 livein xmm4/5 を
  同じ CFG 解析で求める。G の入口 livein xmm4/5 が 1 以上なら「未定義のまま渡された値を G が要求する」候補。
  F の入口 livein には現れないため、mx6 の母集合 (livein 17) の外側に出る。
"""
import bisect
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import capstone  # noqa: E402
import pefile  # noqa: E402
from capstone import x86  # noqa: E402

from mx6_vectorcall import VOLATILE, analyze, bits, effects  # noqa: E402


def main(pe_path, seeds_p, out_p):
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
    entry_cache = {}

    def entry_livein45(va_rva):
        if va_rva not in entry_cache:
            e = fn_end(va_rva)
            code = data[off(va_rva):off(va_rva) + (e - va_rva)]
            r = analyze(md, code, base + va_rva, base + e, read_abs)
            entry_cache[va_rva] = None if r is None else (r['livein'] & 0x30)
        return entry_cache[va_rva]

    def may_before(insns, succ, eff):
        """各命令の直前で xmm4/5 が (いずれかの経路で) 定義済みかの集合 (may)。
        併せて、直前のいずれかの経路に call があるか (call は xmm0〜5 を clobber しうる) を返す。"""
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

    fwd = []
    stats = {'F_analyzed': 0, 'F_with_direct_site': 0, 'sites_reachable': 0,
             'sites_after_call_excluded': 0, 'sites_undefined45': 0, 'G_livein45_nonzero': 0,
             'G_outside_text_or_unanalyzable': 0, 'G_pdata_begin': 0}
    for F in sorted(set(seeds)):
        if F not in funcs:
            continue
        e = fn_end(F)
        code = data[off(F):off(F) + (e - F)]
        r = analyze(md, code, base + F, base + e, read_abs)
        if r is None:
            continue
        stats['F_analyzed'] += 1
        insns, succ = r['cfg']
        n = len(insns)
        eff = []
        for ins in insns:
            rd, wr = effects(md, ins)
            is_call = bool(ins.group(x86.X86_GRP_CALL))
            if is_call:
                wr |= VOLATILE
            eff.append((rd, wr, is_call))
        may, called = may_before(insns, succ, eff)
        had = False
        for k, ins in enumerate(insns):
            if not (ins.group(x86.X86_GRP_CALL) or ins.group(x86.X86_GRP_JUMP)):
                continue
            if not re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
                continue
            t = int(ins.op_str, 16) - base
            if F <= t < e and not ins.group(x86.X86_GRP_CALL):
                continue  # 関数内ジャンプは対象外
            if may[k] is None:
                continue
            had = True
            stats['sites_reachable'] += 1
            if may[k] & 0x30:
                continue  # 転送前に F が定義している
            if called[k]:
                stats['sites_after_call_excluded'] += 1
                continue  # 前段の call が xmm4/5 を clobber しうるため、入口値との同一性を示せない
            stats['sites_undefined45'] += 1
            if not (t_lo <= t < t_hi):
                stats['G_outside_text_or_unanalyzable'] += 1
                continue
            li = entry_livein45(t)
            if li is None:
                stats['G_outside_text_or_unanalyzable'] += 1
                continue
            if li:
                stats['G_livein45_nonzero'] += 1
                if t in funcs:
                    stats['G_pdata_begin'] += 1
                fwd.append({'F': hex(F), 'site': hex(ins.address - base), 'kind': ins.mnemonic,
                            'G': hex(t), 'G_livein45': bits(li)})
        if had:
            stats['F_with_direct_site'] += 1
    F_set = sorted({x['F'] for x in fwd})
    res = {'seeds_pdata_begin': sum(1 for s in set(seeds) if s in funcs), 'stats': stats,
           'candidate_F_count': len(F_set), 'candidate_F': F_set, 'sites': fwd}
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1)
    print('MX-54 U3e: F analyzed=%d candidate F=%d sites=%d' % (stats['F_analyzed'], len(F_set), len(fwd)))
    print('   stats=%s' % stats)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
