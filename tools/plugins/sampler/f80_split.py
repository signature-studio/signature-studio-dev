#!/usr/bin/env python3
# #742: lea_lift.sh の f80 計数は `\n(?=define )` で切るため、最後の define の後ろにある module 直下の declare
# (__frontend_reg_*.fpr(x86_fp80) 等) がその関数に付く。 本スクリプトは関数本体 (define ... 閉じ括弧) だけで f80 を数え、
# 同じ関数の機械語 (PE の範囲) に x87 命令があるかを capstone で突合する。
#   python3 sampler/f80_split.py <PE> <ranges.txt> <p.final.ll> [<p.final.ll> ...]   (FL_WIN64_DIR は PE の path で渡す)
import os, re, sys
import capstone, pefile

def body_f80(path):
    out, cur, inb = {}, None, False
    for l in open(path).read().splitlines():
        m = re.match(r'^define [^@]*@(\w+)\(', l)
        if m:
            cur, inb = m.group(1), True
            out.setdefault(cur, 0)
            continue
        if inb and l.startswith('}'):
            inb = False
            continue
        if inb and 'x86_fp80' in l:
            out[cur] += 1
    return out

def func_ends(pe, base):
    ends = {}
    for e in getattr(pe, 'DIRECTORY_ENTRY_EXCEPTION', []) or []:
        s = e.struct
        ends[base + s.BeginAddress] = base + s.EndAddress
    return ends

def x87_of(pe, base, md, ranges, va, ends):
    for r in ranges:
        a, b = r
        if a <= va < b:
            end = min(ends[va], b) if va in ends else b
            code = pe.get_data(va - base, end - va)
            out = set()
            for i in md.disasm(code, va):
                if i.address >= end:
                    break
                if i.mnemonic.startswith('f'):
                    out.add(i.mnemonic)
                if va not in ends and i.mnemonic.startswith('ret'):
                    break
            return sorted(out)
    return None

def main():
    pe_path, rng_path, lls = sys.argv[1], sys.argv[2], sys.argv[3:]
    pe = pefile.PE(pe_path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    ends = func_ends(pe, base)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ranges = [tuple(int(x, 16) for x in r.split('-')) for r in open(rng_path).read().strip().split(',')]
    for ll in lls:
        f = body_f80(ll)
        hits = {k: v for k, v in f.items() if v}
        print(f'{ll}: defines={len(f)} body_f80_funcs={len(hits)} {hits}')
        for k in sorted(hits):
            va = int(k.rsplit('function_', 1)[1], 16) if k.startswith('function_') else None
            if va is None:
                continue
            print(f'  {k}: machine x87 mnemonics={x87_of(pe, base, md, ranges, va, ends)}')

if __name__ == '__main__':
    main()
