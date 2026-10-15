#!/usr/bin/env python3
"""élastique_x64.dll の IPPCODE 内の間接 call 宛先の IPP 同定 (T-SH-80 / #3420)。

既定は #3334 の付録 §9.5 の組: 分岐元 0x1803c480a (`call rax`) と宛先 0x1803c4710。
入力 (ipp_entries.py と同じ): ELASTIQUE_DLL・DSP_IPP_DLL。出力は標準出力のみ (ファイルは書かない)。

同定の根拠は正規化命令列 (ipp_entries.tokens) の SHA-1 完全一致だけ。近似比は使わない。
- [1] 宛先と、分岐元を含む関数の本体。分岐元の関数先頭は、分岐元より前の直近の ret の後 (IPPCODE に pdata は無い)。
- [2] ipp_entries.py と同じ候補集合との照合。既存の reach は direct_calls が最初の ret で止まるため、
      早期 ret の後の呼出しを辿らない。
- [3] dsp_ippv2 の IPPCODE 全体で、同じ先頭 7 byte を持つ位置を列挙して SHA-1 を照合する。
- [4] 一致した dsp 本体の呼出元を rel32 で逆に辿り、export 名 (または dispatch 表の変種) に当たるまで遡る。
"""
import argparse
import bisect
import collections
import csv
import os
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

import ipp_entries as ie

TARGET = 0x1803c4710
SITE = 0x1803c480a
MATRIX = os.path.join(ie.HERE, '..', '..', 'ipp', 'data', 'ipp_matrix.csv')


def sweep_range(img, md, lo, hi, on_ins):
    mem, base = img['mem'], img['base']
    CH = 1 << 16
    pos = lo
    while pos < hi:
        end = min(hi, pos + CH)
        last = None
        for ins in md.disasm(mem[pos:min(end + 16, len(mem))], base + pos):
            rva = ins.address - base
            if rva >= end:
                break
            last = rva + ins.size
            on_ins(rva, ins)
        pos = last if last is not None and last > pos else pos + 1


def fn_start_before(img, md, site):
    state = {'start': img['ipp_lo'], 'after_ret': False}

    def on(rva, ins):
        if rva >= site:
            return
        if ins.mnemonic == 'ret':
            state['after_ret'] = True
        elif state['after_ret'] and ins.mnemonic not in ('nop', 'int3'):
            state['start'] = rva
            state['after_ret'] = False
    sweep_range(img, md, img['ipp_lo'], site, on)
    return state['start']


def fn_end(img, md, rva, maxins=ie.MAXINS):
    mem, base = img['mem'], img['base']
    for n, ins in enumerate(md.disasm(mem[rva:rva + maxins * 15], base + rva)):
        if ins.mnemonic == 'ret' or n + 1 >= maxins:
            return ins.address - base + ins.size
    return rva


def copies_in_ipp(img, md, prefix, sha_want):
    mem = img['mem']
    out = []
    i = mem.find(prefix, img['ipp_lo'], img['ipp_hi'])
    while i != -1:
        if ie.sha(ie.tokens(img, md, i)) == sha_want:
            out.append(i)
        i = mem.find(prefix, i + 1, img['ipp_hi'])
    return out


def dsp_candidates(dsp, md, depth):
    exports = [(s.name.decode(), s.address) for s in dsp['pe'].DIRECTORY_ENTRY_EXPORT.symbols if s.name]
    roots = {name: ie.dispatch_table(dsp, md, rva) for name, rva in exports}
    reached = ie.reach(dsp, md, roots, depth=depth)
    origin = collections.defaultdict(set)
    for f, (_, org) in reached.items():
        origin[f] |= org
    for f in ie.rel_targets(dsp, md):
        origin.setdefault(f, set())
    by_sig = collections.defaultdict(list)
    for f in origin:
        by_sig[ie.sha(ie.tokens(dsp, md, f))].append(f)
    return origin, by_sig, exports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=lambda s: int(s, 16), default=TARGET)
    ap.add_argument('--site', type=lambda s: int(s, 16), default=SITE)
    ap.add_argument('--depth', type=int, default=ie.REACH_DEPTH)
    args = ap.parse_args()

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    elq = ie.load(ie.ELQ)
    dsp = ie.load(ie.DSP)
    base, dbase = elq['base'], dsp['base']
    print(f'elastique: {ie.ELQ}')
    print(f'dsp_ippv2: {ie.DSP}')

    tgt = args.target - base
    fn = fn_start_before(elq, md, args.site - base)
    fend = fn_end(elq, md, fn)
    tok_t = ie.tokens(elq, md, tgt)
    tok_f = ie.tokens(elq, md, fn)
    print(f'[1] 宛先 {args.target:#x}: 正規化 {len(tok_t)} 命令 SHA-1 {ie.sha(tok_t)}')
    print(f'    分岐元 {args.site:#x} の関数 {base + fn:#x}-{base + fend:#x}: 正規化 {len(tok_f)} 命令 SHA-1 {ie.sha(tok_f)}')

    lea = collections.defaultdict(list)
    rel = collections.defaultdict(list)
    ind = []

    def on(rva, ins):
        if ins.mnemonic == 'lea' and 'rip' in ins.op_str:
            t = rva + ins.size + int.from_bytes(ins.bytes[-4:], 'little', signed=True)
            if elq['ipp_lo'] <= t < elq['ipp_hi']:
                lea[t].append(rva)
        if ins.mnemonic in ('call', 'jmp') and ins.bytes[0] in (0xE8, 0xE9) and ins.size == 5:
            rel[rva + 5 + int.from_bytes(ins.bytes[1:5], 'little', signed=True)].append(rva)
        if ins.mnemonic in ('call', 'jmp') and not ins.op_str.startswith('0x'):
            ind.append(rva)
    sweep_range(elq, md, elq['text_lo'], elq['text_hi'], on)
    sweep_range(elq, md, elq['ipp_lo'], elq['ipp_hi'], on)
    print(f'    宛先を指す lea rip: {[hex(base + r) for r in lea[tgt]]}')
    print(f'    宛先を指す rel32 call/jmp: {len(rel[tgt])} 箇所')
    fn_lea = sorted((r, t) for t, rs in lea.items() for r in rs if fn <= r < fend)
    print(f'    分岐元の関数内の lea rip (IPPCODE 宛先): ' + ', '.join(f'{base + r:#x}->{base + t:#x}' for r, t in fn_lea))
    ind_ipp = [r for r in ind if elq['ipp_lo'] <= r < elq['ipp_hi']]
    print(f'    IPPCODE 内の間接 call/jmp (レジスタ・メモリ経由): {len(ind_ipp)} 箇所')

    origin, by_sig, exports = dsp_candidates(dsp, md, args.depth)
    print(f'[2] 既存の照合 (ipp_entries.py と同じ候補集合): export {len(exports)}・reach {args.depth} 段・候補 {len(origin)} 本体')
    for label, tok in (('宛先', tok_t), ('分岐元の関数', tok_f)):
        m = sorted(by_sig.get(ie.sha(tok), []))
        names = sorted({n for v in m for n in origin.get(v, ())})
        print(f'    {label}: 完全一致 {len(m)} 本体・export 名 {names or "なし"}')

    print('[3] 広い照合 (dsp IPPCODE 全体で同じ先頭 7 byte の位置を SHA-1 で照合)')
    tgt_copies = copies_in_ipp(dsp, md, bytes(elq['mem'][tgt:tgt + 7]), ie.sha(tok_t))
    fn_copies = copies_in_ipp(dsp, md, bytes(elq['mem'][fn:fn + 7]), ie.sha(tok_f))
    print(f'    宛先: 完全一致 {len(tgt_copies)} 件 {[hex(dbase + c) for c in tgt_copies]}')
    print(f'    分岐元の関数: 完全一致 {len(fn_copies)} 件 {[hex(dbase + c) for c in fn_copies]}')

    dlea = collections.defaultdict(list)

    def on_d(rva, ins):
        if ins.mnemonic == 'lea' and 'rip' in ins.op_str:
            t = rva + ins.size + int.from_bytes(ins.bytes[-4:], 'little', signed=True)
            dlea[t].append(rva)
    sweep_range(dsp, md, dsp['text_lo'], dsp['text_hi'], on_d)
    sweep_range(dsp, md, dsp['ipp_lo'], dsp['ipp_hi'], on_d)
    for c in tgt_copies:
        for fc in fn_copies:
            fe = fn_end(dsp, md, fc)
            for r in dlea.get(c, []):
                if fc <= r < fe:
                    print(f'    dsp の lea {dbase + r:#x} -> {dbase + c:#x} は分岐元の関数の完全一致 {dbase + fc:#x} 内')

    other = sorted({fn_start_before(elq, md, r) for r in lea[tgt]} - {fn})
    for f2 in other:
        tok2 = ie.tokens(elq, md, f2)
        copies2 = copies_in_ipp(dsp, md, bytes(elq['mem'][f2:f2 + 7]), ie.sha(tok2))
        print(f'    宛先を lea で指す別の関数 {base + f2:#x} ({len(tok2)} 命令・SHA-1 {ie.sha(tok2)[:12]}): '
              f'dsp 完全一致 {[hex(dbase + c) for c in copies2]}')
        fn_copies += copies2

    # [4] dsp の呼出元の逆探索
    rev = collections.defaultdict(set)

    def on_r(rva, ins):
        if ins.mnemonic in ('call', 'jmp') and ins.bytes[0] in (0xE8, 0xE9) and ins.size == 5:
            rev[rva + 5 + int.from_bytes(ins.bytes[1:5], 'little', signed=True)].add(rva)
    sweep_range(dsp, md, dsp['text_lo'], dsp['text_hi'], on_r)
    sweep_range(dsp, md, dsp['ipp_lo'], dsp['ipp_hi'], on_r)
    funcs = sorted(e.struct.BeginAddress for e in dsp['pe'].DIRECTORY_ENTRY_EXCEPTION
                   if dsp['text_lo'] <= e.struct.BeginAddress < dsp['text_hi'])
    exp_rva = {rva: n for n, rva in exports}
    var = collections.defaultdict(set)
    for n, rva in exports:
        for v in ie.dispatch_table(dsp, md, rva):
            var[v].add(n)

    def owner(site_rva):
        i = bisect.bisect_right(funcs, site_rva) - 1
        return funcs[i] if i >= 0 else None

    def up(start, max_depth=6):
        seen = {start: None}
        frontier = [start]
        for _ in range(max_depth):
            nxt = []
            for f in frontier:
                for c in sorted(rev.get(f, ())):
                    o = owner(c)
                    if o is None:
                        continue
                    if o in exp_rva or o in var:
                        chain = [o]
                        x = f
                        while x is not None:
                            chain.append(x)
                            x = seen[x]
                        return (exp_rva.get(o) or sorted(var[o])[0]), chain
                    if o not in seen:
                        seen[o] = f
                        nxt.append(o)
            frontier = nxt
        return None, None

    print('[4] dsp の呼出し経路 (rel32 の直接 call を逆に遡る。export 名または dispatch 変種に当たるまで)')
    names = set()
    for c in fn_copies:
        name, chain = up(c)
        if name is None:
            print(f'    {dbase + c:#x}: 6 段内で export に当たらず')
            continue
        names.add(name)
        print(f'    {dbase + c:#x}: 経路 ' + ' → '.join(f'{dbase + x:#x}' for x in chain) + f' → 名 {name}')

    print('[5] tools/ipp の実装対応 (tools/ipp/data/ipp_matrix.csv の implemented_poc)')
    poc = {r['name']: r['implemented_poc'] == '1' for r in csv.DictReader(open(MATRIX))}
    for name in sorted(names):
        print(f'    {name}: implemented_poc={int(poc.get(name, False))}')


if __name__ == '__main__':
    sys.exit(main())
