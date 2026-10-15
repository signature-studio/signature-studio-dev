#!/usr/bin/env python3
"""T3 Multiband Delay engine (19165) の IPPCODE 節 (静的リンクの IPP と推定) の呼出元・呼出先を静的に切り分ける (#3445 PLG-F4-3)。

測定のみ (判定はしない・実行はしない)。 pefile + capstone。
2 通りで直接 call/jmp の辺を数える:
  P pdata 基準: .pdata の関数 (lift 範囲 = engine_ranges.py と同じ) の中の命令だけを見る。 下限。
  S 線形走査: .text と IPPCODE を先頭から逆アセンブルする (不正命令は 1 byte 飛ばす)。 pdata に載らない IPP 本体を拾う。 上限寄り (データの誤デコードを含みうる)。
区分 (IPPCODE の先頭ごと):
  text   .text 由来の直接 call/jmp がある   ipp  IPPCODE 由来の直接 call/jmp がある
  ptr    データ中の 8 byte / 4 byte の絶対値 (関数ポインタ表の候補) が指す
  addr   コード中の rip 相対参照が指す (関数アドレスの取得の候補)
  none   上のどれも無い (殻・export・間接呼出しのいずれでも静的に辿れない)
呼出元の件数: pdata 関数 (fn) と、pdata 外の呼出し箇所 (site・箇所の VA ごとに 1 件) を別に数える。 pdata 外を 1 件に潰さない。
殻 (block 19164) は engine の DLL 名を import せず、IPPCODE は export されない。 殻からの直接参照は PE 上に作れない (別イメージ)。
usage: ipp_callers.py [--json OUT] [block]
"""
import bisect, collections, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

ENGINE, SHELL = 19165, 19164


def path(block):
    return os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block)


def sweep(md, raw, va):
    """線形走査。 不正命令は 1 byte 飛ばす。 (address, ins) を返す。"""
    out, i = [], 0
    while i < len(raw):
        got = None
        for ins in md.disasm(raw[i:i + 16], va + i, 1):
            got = ins
        if got is None:
            i += 1
            continue
        out.append(got)
        i += got.size
    return out


def analyze(block):
    pe = pefile.PE(path(block), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = {s.Name.rstrip(b'\0').decode(errors='replace'): s for s in pe.sections}
    ipp = secs['IPPCODE']
    ipp_lo, ipp_hi = base + ipp.VirtualAddress, base + ipp.VirtualAddress + ipp.Misc_VirtualSize

    def sec_of(v):
        for n, s in secs.items():
            if base + s.VirtualAddress <= v < base + s.VirtualAddress + s.Misc_VirtualSize:
                return n
        return '-'

    in_ipp = lambda v: ipp_lo <= v < ipp_hi
    pdata = secs['.pdata'].get_data()
    funcs = set()
    for i in range(len(pdata) // 12):
        s, e, u = struct.unpack_from('<III', pdata, 12 * i)
        if s and e > s and not (u & 1):
            funcs.add((base + s, base + e))
    funcs = sorted(funcs)
    starts = [a for a, _ in funcs]
    ends = dict(funcs)
    ipp_starts = {a for a in starts if in_ipp(a)}

    def owner(v):
        i = bisect.bisect_right(starts, v) - 1
        return starts[i] if i >= 0 and v < ends[starts[i]] else None

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    # 命令列: pdata 基準 (関数ごと) と 線形 (節ごと) の 2 通り
    pd_ins = []
    for a, e in funcs:
        for ins in md.disasm(pe.get_data(a - base, e - a), a):
            pd_ins.append((a, ins))
    lin_ins = []
    for name in ('.text', 'IPPCODE'):
        s = secs[name]
        va = base + s.VirtualAddress
        for ins in sweep(md, s.get_data()[:s.Misc_VirtualSize], va):
            lin_ins.append((owner(ins.address), ins))

    def edges(seq):
        direct, rip, ind = [], collections.defaultdict(set), collections.Counter()
        for src, ins in seq:
            cls = 'ipp' if in_ipp(ins.address) else sec_of(ins.address)
            unit = src if src is not None else ('site', ins.address)
            if ins.mnemonic in ('call', 'jmp') and ins.operands:
                o = ins.operands[0]
                if o.type == X86_OP_IMM:
                    if ins.mnemonic == 'jmp' and src is not None and owner(o.imm) == src:
                        continue
                    direct.append((unit, cls, o.imm))
                else:
                    ind[cls] += 1
            for o in ins.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    rip[ins.address + ins.size + o.mem.disp].add(unit)
        return direct, rip, ind

    d_p, rip_p, ind_p = edges([(a, i) for a, i in pd_ins])
    d_s, rip_s, ind_s = edges(lin_ins)
    # データ中の IPP 関数ポインタ (8 byte 絶対値 / 4 byte RVA)
    slots = collections.defaultdict(set)
    for name in ('.rdata', '.data', '_RDATA', 'IPPDATA', '.pdata', '.reloc'):
        s = secs.get(name)
        if s is None:
            continue
        raw = s.get_data()
        sv = base + s.VirtualAddress
        for i in range(0, len(raw) - 7, 8):
            v = struct.unpack_from('<Q', raw, i)[0]
            if v in ipp_starts:
                slots[sv + i].add(v)
        if name not in ('.pdata', '.reloc'):
            for i in range(0, len(raw) - 3, 4):
                v = base + struct.unpack_from('<I', raw, i)[0]
                if v in ipp_starts:
                    slots[sv + i].add(v)
    ptr_entries = {v for vs in slots.values() for v in vs}

    def per_entry(direct):
        by = collections.defaultdict(lambda: {'text': set(), 'ipp': set()})
        for unit, cls, t in direct:
            if in_ipp(t):
                by[t]['ipp' if cls == 'ipp' else 'text'].add(unit)
        return by

    def counts(units):
        fn = sum(1 for u in units if not isinstance(u, tuple))
        return fn, len(units) - fn

    by_p, by_s = per_entry(d_p), per_entry(d_s)
    rows = []
    cls_p, cls_s = collections.Counter(), collections.Counter()
    for a in sorted(ipp_starts):
        k = {}
        for tag, by in (('p', by_p), ('s', by_s)):
            d = by.get(a)
            if d and d['text'] and d['ipp']:
                k[tag] = 'text+ipp'
            elif d and d['text']:
                k[tag] = 'text'
            elif d and d['ipp']:
                k[tag] = 'ipp'
            elif a in ptr_entries:
                k[tag] = 'ptr'
            elif rip_s.get(a) or rip_p.get(a):
                k[tag] = 'addr'
            else:
                k[tag] = 'none'
        cls_p[k['p']] += 1
        cls_s[k['s']] += 1
        e = by_s.get(a, {'text': set(), 'ipp': set()})
        (tf, ts), (pf, ps) = counts(e['text']), counts(e['ipp'])
        rows.append({'va': hex(a), 'end': hex(ends[a] - a), 'class_pdata': k['p'], 'class_linear': k['s'],
                     'text_callers_linear': tf, 'text_outside_sites_linear': ts,
                     'ipp_callers_linear': pf, 'ipp_outside_sites_linear': ps})
    # 非 pdata の IPP 着地点 (線形で見つかるが pdata 先頭ではないもの)
    landings = {t for _, _, t in d_s if in_ipp(t)}
    non_pdata = sorted(t for t in landings if t not in ipp_starts)
    gap = [t for t in non_pdata if owner(t) is None]
    inside = [t for t in non_pdata if owner(t) is not None]
    # IPPCODE 外への直接辺 (線形・pdata 基準)
    out_p = [(s, t) for s, c, t in d_p if c == 'ipp' and not in_ipp(t)]
    out_s = [(s, t) for s, c, t in d_s if c == 'ipp' and not in_ipp(t)]
    # export から直接辺だけで到達する (pdata 基準の下限)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    exports = [base + e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    succ = collections.defaultdict(set)
    for src, c, t in d_p:
        if src is not None and owner(t) is not None:
            succ[src].add(owner(t))
    reach, todo = set(), []
    for x in exports:
        o = owner(x)
        if o is not None and o not in reach:
            reach.add(o)
            todo.append(o)
    while todo:
        f = todo.pop()
        for g in succ.get(f, ()):
            if g not in reach:
                reach.add(g)
                todo.append(g)
    tx_fn, tx_site = counts({s for s, c, t in d_s if c != 'ipp' and in_ipp(t)})
    return {
        'block': block, 'ipp_range': [hex(ipp_lo), hex(ipp_hi)], 'ipp_size': ipp.Misc_VirtualSize,
        'ipp_pdata_funcs': len(ipp_starts), 'ipp_pdata_bytes': sum(ends[a] - a for a in ipp_starts),
        'text_pdata_funcs': len(starts) - len(ipp_starts),
        'pdata_edges_into_ipp': sum(1 for _, _, t in d_p if in_ipp(t)),
        'linear_edges_into_ipp': sum(1 for _, _, t in d_s if in_ipp(t)),
        'linear_entries_into_ipp': len(landings), 'linear_entries_at_pdata_start': len(landings & ipp_starts),
        'linear_entries_inside_pdata_func': len(inside), 'linear_entries_outside_pdata': len(gap),
        'linear_text_callers': tx_fn, 'linear_text_outside_sites': tx_site,
        'class_pdata_basis': dict(cls_p), 'class_linear_basis': dict(cls_s),
        'ptr_slots': len(slots), 'ptr_slot_sections': dict(collections.Counter(sec_of(s) for s in slots)),
        'ptr_entries': len(ptr_entries),
        'ipp_outward_pdata': len(out_p), 'ipp_outward_linear': len(out_s),
        'ipp_outward_linear_targets': dict(collections.Counter(sec_of(t) for _, t in out_s)),
        'indirect_call_sites_pdata': dict(ind_p), 'indirect_call_sites_linear': dict(ind_s),
        'exports': [hex(x) for x in exports], 'export_reach_pdata_funcs': len(reach),
        'export_reach_ipp_pdata_funcs': len(reach & ipp_starts),
        'gap_landings': [hex(t) for t in gap],
        'gap_landing_callers': {hex(t): counts({s for s, c, v in d_s if c != 'ipp' and v == t}) for t in gap},
        'rows': rows,
        'slots': {hex(s): [hex(v) for v in sorted(vs)] for s, vs in sorted(slots.items())},
    }


def shell_strings(block):
    data = open(path(block), 'rb').read()
    res = {}
    for kw in ('engine_x64', 'VSTPluginMain', 'LoadLibrary', 'GetProcAddress', 'dsp_ipp', 'ippsFFT', 'ipps'):
        res[kw] = {'ascii': data.count(kw.encode()), 'utf16': data.count(kw.encode('utf-16le'))}
    return res


def main(argv):
    out = None
    if argv[:1] == ['--json']:
        out, argv = argv[1], argv[2:]
    block = int(argv[0]) if argv else ENGINE
    R = {'engine': analyze(block), 'strings': {str(SHELL): shell_strings(SHELL), str(ENGINE): shell_strings(ENGINE)}}
    for k, v in R['engine'].items():
        if k not in ('rows', 'slots', 'gap_landings'):
            print(k, v)
    print('gap_landings', len(R['engine']['gap_landings']), R['engine']['gap_landings'][:12])
    print('strings', json.dumps(R['strings'], ensure_ascii=False))
    if out:
        with open(out, 'w') as f:
            json.dump(R, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
