#!/usr/bin/env python3
"""MX-53 (#4992) U3b / U3c: 解析できない root・間接 jmp の由来を数える (MX-6 の未解決の出所の測定)。

  U3c: mx6_vectorcall.main が analyze() で捨てる root (先頭から 0 命令しかデコードできない root) の由来。
       - 出所: seeds の pdata 関数の線形走査で、その root へ直接 call/jmp (E8/E9) する命令があるか
       - 出所の命令境界: 出所の命令が、出所関数の先頭からの線形デコードで命令境界か
       - root の位置: root が .pdata の関数内にあり、その関数の先頭からの線形デコードで命令境界か
  U3b: 間接 jmp の解決器 (mx6_vectorcall.jt_targets) が解決できない jmp の形。

usage: mx6_origin_u3.py <pe> <roots_seeds.json> <roots_one.json> <out.json>
       mx6_origin_u3.py --selftest
"""
import bisect
import collections
import json
import re
import sys

import capstone
import pefile
from capstone import x86

import mx6_vectorcall as V


def boundary_set(md, code, base_va, base):
    """code の線形デコードの命令境界 (RVA の集合)。"""
    return set(i.address - base for i in md.disasm(code, base_va))


def selftest():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    base = 0x1000
    # 90 (nop) / c7 48 (c7 /1 は 64bit で不正形: capstone は以降を復号しない)
    code = bytes.fromhex('90c748')
    cases = [
        ('pos: 命令境界 0x1000 (nop) は復号できる', base, True),
        ('pos: 不正形の途中 0x1001 は命令境界でない', base + 1, False),
    ]
    b = boundary_set(md, code, base, 0)
    ok = True
    for name, target, want in cases:
        got = target in b
        ok &= got == want
        print('  %-48s boundary=%s want=%s %s' % (name, got, want, 'PASS' if got == want else 'FAIL'))
    print('selftest %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def classify_jmp(insns, k):
    """解決できない間接 jmp の形。"""
    ins = insns[k]
    if ins.op_str.startswith('qword ptr [') or ins.op_str.startswith('dword ptr ['):
        return 'mem_indirect'
    window = range(max(0, k - 8), k)
    if any(insns[q].mnemonic == 'movsxd' for q in window) and any(insns[q].mnemonic == 'add' for q in window):
        return 'table_shape_unmatched'
    return 'reg_no_table'


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

    # 1) 直接参照の出所: seeds の pdata 関数の線形走査 (mx_entry_surface と同じ走査)
    src = collections.defaultdict(list)
    for e in sorted(set(seeds)):
        if e not in funcs:
            continue
        end = funcs[e][0]
        for a, _iz, mn, ops in md.disasm_lite(data[off(e):off(e) + (end - e)], base + e):
            if mn in ('call', 'jmp') and ops.startswith('0x'):
                src[int(ops, 16) - base].append((e, a - base))

    # U3c: 先頭デコード 0 命令の root
    u3c = collections.Counter()
    u3c['roots_unique'] = len(set(one))
    bset = {}

    def containing_bounds(c):
        if c not in bset:
            bset[c] = boundary_set(md, data[off(c):off(c) + (funcs[c][0] - c)], base + c, base)
        return bset[c]

    for va in sorted(set(one)):
        if not (t_lo <= va < t_hi):
            u3c['outside_text'] += 1
            continue
        e = fn_end(va)
        if len(list(md.disasm(data[off(va):off(va) + (e - va)], base + va))) > 0:
            j = bisect.bisect_right(begins, va) - 1
            if j >= 0 and va < funcs[begins[j]][0]:
                u3c['nc_decodable_in_containing_fn'] += 1
                if va in containing_bounds(begins[j]):
                    u3c['nc_decodable_boundary_in_containing_fn'] += 1
            continue
        u3c['no_own_decode'] += 1
        s = src.get(va, [])
        if s:
            u3c['has_seed_direct_source'] += 1
            f, a = s[0]
            if a in containing_bounds(f):
                u3c['source_is_insn_boundary'] += 1
        j = bisect.bisect_right(begins, va) - 1
        if j >= 0 and va < funcs[begins[j]][0]:
            u3c['containing_pdata_fn'] += 1
            if va in containing_bounds(begins[j]):
                u3c['boundary_in_containing_fn'] += 1
        else:
            u3c['outside_pdata_fn'] += 1

    # U3b: 解決できない間接 jmp (= analyze の unknown_flow)
    u3b = {}
    for label, roots in (('seeds', seeds), ('one_round', one)):
        shapes = collections.Counter()
        fns_unknown = 0
        fns_unknown_pdata_begin = 0
        for va in sorted(set(roots)):
            if not (t_lo <= va < t_hi):
                continue
            e = fn_end(va)
            insns = list(md.disasm(data[off(va):off(va) + (e - va)], base + va))
            if not insns:
                continue
            unknown = False
            for k, ins in enumerate(insns):
                if not ins.group(x86.X86_GRP_JUMP) or re.fullmatch(r'0x[0-9a-f]+', ins.op_str):
                    continue
                if V.jt_targets(insns, k, read_abs) is None:
                    unknown = True
                    shapes[classify_jmp(insns, k)] += 1
            if unknown:
                fns_unknown += 1
                if va in funcs:
                    fns_unknown_pdata_begin += 1
        u3b[label] = {'unknown_flow_fns': fns_unknown,
                      'unknown_flow_fns_pdata_begin': fns_unknown_pdata_begin,
                      'unresolved_jmp_shapes': dict(shapes)}

    res = {'U3c': dict(u3c), 'U3b': u3b}
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--selftest':
        sys.exit(selftest())
    sys.exit(main(*sys.argv[1:5]))
