#!/usr/bin/env python3
"""framework 共通の `dsp_ippv2.dll` 文字列が「実使用」かを plugin ごとに静的に調べる (#201 Convolver の FFT 依存確認)。

方式 (capstone, .pdata 関数単位の逆アセンブル):
  1. IPP ローダ関数 = Delphi UnicodeString literal `dsp_ipp*` / `ipp*` を rip 相対で参照する関数のうち、`lea rdx,[rip+VAR]` の直後 (3 命令以内) に
     `lea r8,[rip+NAME]` (NAME = ipp* literal) が現れるもの。 VAR = 関数ポインタ変数 (IPP 関数 NAME の格納先) → 変数表 G を得る。
  2. 全 .pdata 関数を走査し、ローダ以外で G の変数を rip 相対で参照する関数を求める (= IPP 関数ポインタを使うコード)。
  3. その関数が 閉包 (work/closure/block*.ranges.txt) / frontier (block*.json の frontier) / それ以外 のどれか、
     および 閉包から直接 call/jmp rel32 だけで到達できる関数集合 (BFS; 間接 call は辿らない = 下限) に入るかを数える。
出力: JSON (--json) と 1 行/plugin の表。 判定はしない (測定のみ)。 到達しない = IPP 不使用 ではない (vcall / ptr 呼出は辿らないため)。
usage: ipp_use.py [--json OUT] [--closure-dir DIR] <block> ...
補助: 変数表 G の [min,max+8) 内で G に含まれない rip 相対参照 (配列として添字参照されている疑い) の関数数を `users_in_slot_range_not_exact` に出す。
"""
import collections, json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
CLOSURE_DIR = os.path.join(W, 'closure')
HDR = re.compile(rb'\xb0\x04\x02\x00\xff\xff\xff\xff(.{4})', re.S)


def literals(pe, data):
    base = pe.OPTIONAL_HEADER.ImageBase

    def off2va(off):
        for s in pe.sections:
            if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                return base + s.VirtualAddress + off - s.PointerToRawData
    out = {}
    for m in HDR.finditer(data):
        n = struct.unpack('<I', m.group(1))[0]
        if 0 < n < 64:
            try:
                t = data[m.end():m.end() + 2 * n].decode('utf-16le')
            except UnicodeDecodeError:
                continue
            if re.match(r'^(ipp|dsp_ipp)', t, re.I):
                out[off2va(m.end())] = t
    return out


def analyze(block):
    path = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block)
    data = open(path, 'rb').read()
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    lits = literals(pe, data)
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = []
    for i in range(len(pd) // 12):
        s, e, u = struct.unpack_from('<III', pd, 12 * i)
        if s and not (u & 1) and e > s:
            funcs.append((base + s, base + e))
    funcs = sorted(set(funcs))
    starts = {a for a, _ in funcs}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    memrefs, callees = {}, {}
    loader_vars = {}
    loaders = []
    for (a, e) in funcs:
        refs, cal = set(), set()
        pend = None
        ninstr = 0
        lit_refs = 0
        pairs = {}
        for ins in md.disasm(pe.get_data(a - base, e - a), a):
            ninstr += 1
            if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == X86_OP_IMM:
                t = ins.operands[0].imm
                if t in starts:
                    cal.add(t)
            tgt = None
            for o in ins.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    tgt = ins.address + ins.size + o.mem.disp
                    refs.add(tgt)
            if ins.mnemonic == 'lea' and tgt is not None:
                if ins.reg_name(ins.operands[0].reg) == 'rdx':
                    pend = (tgt, ninstr)
                elif ins.reg_name(ins.operands[0].reg) == 'r8' and tgt in lits and pend and ninstr - pend[1] <= 3:
                    pairs[pend[0]] = lits[tgt]
                    pend = None
            if tgt in lits:
                lit_refs += 1
        memrefs[a] = refs
        callees[a] = cal
        if pairs:
            loaders.append((a, e, len(pairs)))
            loader_vars.update(pairs)
    G = set(loader_vars)
    lo_g, hi_g = (min(G), max(G) + 8) if G else (0, 0)
    in_range = {a for a, refs in memrefs.items() if a not in {x for x, _, _ in loaders} and any(lo_g <= r < hi_g and r not in G for r in refs)}
    loader_set = {a for a, _, _ in loaders}
    user = {a: sorted({loader_vars[v] for v in refs & G}) for a, refs in memrefs.items() if a not in loader_set and refs & G}
    c = json.load(open(os.path.join(CLOSURE_DIR, 'block%05d.json' % block)))
    clo_starts = set()
    clo_ranges = []
    for r in c['ranges']:
        x, y = (int(v, 16) for v in r.split('-'))
        clo_ranges.append((x, y))
    for a, _ in funcs:
        if any(x <= a <= y for x, y in clo_ranges):
            clo_starts.add(a)
    fr = {int(x, 16) for x in c['frontier']}
    reach, todo = set(clo_starts), list(clo_starts)
    while todo:
        f = todo.pop()
        for t in callees.get(f, ()):
            if t not in reach:
                reach.add(t)
                todo.append(t)
    u_clo = {a: n for a, n in user.items() if a in clo_starts}
    u_fr = {a: n for a, n in user.items() if a in fr}
    u_reach = {a: n for a, n in user.items() if a in reach and a not in clo_starts}
    names = lambda d: sorted({n for v in d.values() for n in v})
    fft = lambda ns: [n for n in ns if re.search(r'fft|dft|conv|corr', n, re.I)]
    return {
        'block': block, 'ipp_literals': len(lits), 'loader_funcs': [{'va': hex(a), 'bytes': e - a, 'slots': n} for a, e, n in loaders],
        'ipp_slots': len(G), 'slot_va_range': [hex(lo_g), hex(hi_g)], 'users_in_slot_range_not_exact': len(in_range), 'users_total': len(user), 'closure_funcs': len(clo_starts),
        'users_in_closure': len(u_clo), 'names_in_closure': names(u_clo),
        'users_in_frontier': len(u_fr), 'names_in_frontier': names(u_fr),
        'direct_reach_funcs': len(reach), 'users_in_direct_reach_outside_closure': len(u_reach),
        'names_in_direct_reach_outside_closure': names(u_reach),
        'fft_like_names_in_closure_or_reach': fft(names(u_clo) + names(u_reach) + names(u_fr)),
        'user_vas': {hex(a): n for a, n in sorted(user.items())},
    }


def main(argv):
    global CLOSURE_DIR
    out = None
    while argv[:1] and argv[0].startswith('--'):
        if argv[0] == '--json':
            out = argv[1]
        elif argv[0] == '--closure-dir':
            CLOSURE_DIR = argv[1]
        else:
            print('unknown option', argv[0], file=sys.stderr)
            return 2
        argv = argv[2:]
    R = {}
    for b in map(int, argv):
        r = analyze(b)
        R[b] = r
        print('%d ipp_slots=%d (va %s-%s) loader=%s users_total(DLL 全体)=%d slot範囲内の非exact参照関数=%d closure=%d: users_in_closure=%d frontier=%d direct_reach(outside closure)=%d  closure names=%s frontier names=%s reach names=%s' % (
            b, r['ipp_slots'], r['slot_va_range'][0], r['slot_va_range'][1], [x['va'] for x in r['loader_funcs']], r['users_total'], r['users_in_slot_range_not_exact'],
            r['closure_funcs'], r['users_in_closure'], r['users_in_frontier'],
            r['users_in_direct_reach_outside_closure'], r['names_in_closure'], r['names_in_frontier'], r['names_in_direct_reach_outside_closure']))
    if out:
        json.dump(R, open(out, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
