#!/usr/bin/env python3
"""élastique_x64.dll の静的 IPP 節 (IPPCODE) の入口を列挙し、FL 同梱 dsp_ippv2_x64.dll の本体と照合する (T-SH-40 / #2613)。

入力 (既定):
  ELASTIQUE_DLL  = tools/shared/work/win/elastique_x64.dll (FL 素材 block24357_PE.bin の複製)
  DSP_IPP_DLL    = $FL_WIN64_DIR/extracted/block24356_PE.bin (dsp_ippv2_x64.dll, export 446)
出力: tools/shared/work/elastique/facts.json (gitignore)。標準出力に集計。

- 入口 = .text を線形走査して得た call/jmp rel32 の着地点のうち IPPCODE 節内のもの (distinct)。
- dsp 側の export は `movsxd rax,[rip+X]; lea r10,[rip+T]; jmp [r10+rax*8]` の CPU 別ディスパッチで、
  表 T の各項が variant 本体。export 名 → variant 本体 (表の全項) を対応表にする。
- 照合 = 本体の正規化命令列 (分岐先・rip 相対変位・大きな即値を伏せる) の SHA-1 一致。一致しなければ
  variant 集合に対する bigram Jaccard で上位を取り SequenceMatcher の比を出す (参考値、一致扱いはしない)。
- 出力: data/entries.csv (197 行の対応表・コミット対象) と tools/shared/work/elastique/facts.json (中間物・gitignore)。
- 関数ポインタ経由の到達: .text の lea rip 相対で IPPCODE を指す箇所・間接 call/jmp・
  .rdata/.data 中の IPPCODE 向き 8 byte 値を数え、入口集合との差を出す (静的確認。実行トレースではない)。
"""
import collections
import csv
import difflib
import hashlib
import json
import os
import re
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work', 'elastique')
ELQ = os.environ.get('ELASTIQUE_DLL', os.path.join(HERE, '..', 'work', 'win', 'elastique_x64.dll'))
DSP = os.environ.get('DSP_IPP_DLL') or os.path.join(
    os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block24356_PE.bin')
MAXINS = 200
TABLE_MAX = 16
REACH_DEPTH = 12
TRIVIAL = 8
RIP = re.compile(r'\[rip [+-] 0x[0-9a-f]+\]')
HEX = re.compile(r'0x[0-9a-f]+')


def load(path):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    secs = {s.Name.rstrip(b'\0').decode(errors='replace'): s for s in pe.sections}
    img = {'base': pe.OPTIONAL_HEADER.ImageBase, 'mem': pe.get_memory_mapped_image(), 'pe': pe, 'secs': secs}
    for k, n in (('ipp', 'IPPCODE'), ('text', '.text')):
        img[k + '_lo'] = secs[n].VirtualAddress
        img[k + '_hi'] = img[k + '_lo'] + secs[n].Misc_VirtualSize
    return img


def in_code(img, rva):
    return img['text_lo'] <= rva < img['text_hi'] or img['ipp_lo'] <= rva < img['ipp_hi']


def sweep(img, md, on_ins):
    """.text の線形走査。invalid byte は 1 byte 飛ばす。"""
    mem, base = img['mem'], img['base']
    lo, hi = img['text_lo'], img['text_hi']
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


def rel_targets(img, md):
    hits = collections.defaultdict(list)

    def on(rva, ins):
        if ins.bytes[0] in (0xE8, 0xE9) and ins.size == 5:
            t = rva + 5 + int.from_bytes(ins.bytes[1:5], 'little', signed=True)
            if img['ipp_lo'] <= t < img['ipp_hi']:
                hits[t].append(rva)
    sweep(img, md, on)
    return hits


def tokens(img, md, rva, maxins=MAXINS):
    """rva から線形に正規化命令列を取る。ret で止まる。"""
    mem, base = img['mem'], img['base']
    out = []
    for ins in md.disasm(mem[rva:rva + maxins * 15], base + rva):
        op = ins.op_str
        if (ins.mnemonic == 'call' or ins.mnemonic[0] == 'j') and op.startswith('0x'):
            op = 'T'
        op = RIP.sub('[rip]', op)
        op = HEX.sub(lambda m: m.group(0) if len(m.group(0)) <= 6 else 'A', op)
        out.append(f'{ins.mnemonic} {op}')
        if ins.mnemonic == 'ret' or len(out) >= maxins:
            break
    return out


def ptr_at(img, va):
    mem = img['mem']
    return int.from_bytes(mem[va - img['base']:va - img['base'] + 8], 'little')


def follow(img, md, rva, hops=4):
    """先頭が直接 jmp rel32 の thunk なら着地点へ、jmp [rip+x] なら格納ポインタを追う。"""
    mem, base = img['mem'], img['base']
    seen = [rva]
    for _ in range(hops):
        ins = next(md.disasm(mem[rva:rva + 16], base + rva), None)
        if ins is None:
            break
        if ins.mnemonic == 'jmp' and ins.bytes[0] == 0xE9:
            t = rva + 5 + int.from_bytes(ins.bytes[1:5], 'little', signed=True)
        elif ins.mnemonic == 'jmp' and ins.bytes[:2] == b'\xff\x25':
            slot = rva + ins.size + int.from_bytes(ins.bytes[2:6], 'little', signed=True)
            t = ptr_at(img, base + slot) - base
        else:
            break
        if not in_code(img, t):
            break
        rva = t
        seen.append(rva)
    return rva, seen


def dispatch_table(img, md, rva):
    """export 先頭の `movsxd; lea r10,[rip+T]; jmp [r10+rax*8]` なら表 T の variant RVA 列を返す。"""
    mem, base = img['mem'], img['base']
    i0 = next(md.disasm(mem[rva:rva + 16], base + rva), None)
    if i0 is None or i0.mnemonic != 'movsxd':
        return [rva]
    r1 = rva + i0.size
    i1 = next(md.disasm(mem[r1:r1 + 16], base + r1), None)
    if i1 is None or i1.mnemonic != 'lea' or 'rip' not in i1.op_str:
        return [rva]
    T = r1 + i1.size + int.from_bytes(i1.bytes[-4:], 'little', signed=True)
    out = []
    for k in range(TABLE_MAX):
        v = ptr_at(img, base + T + 8 * k) - base
        if not in_code(img, v):
            break
        out.append(v)
    return out or [rva]


def direct_calls(img, md, rva, maxins=MAXINS):
    """本体から線形に読み、rel32 の call 先のうち .text / IPPCODE 内のものを返す (ret まで)。"""
    mem, base = img['mem'], img['base']
    out = []
    for n, ins in enumerate(md.disasm(mem[rva:rva + maxins * 15], base + rva)):
        if ins.mnemonic == 'call' and ins.bytes[0] == 0xE8 and ins.size == 5:
            t = ins.address - base + 5 + int.from_bytes(ins.bytes[1:5], 'little', signed=True)
            if in_code(img, t):
                out.append(t)
        if ins.mnemonic == 'ret' or n >= maxins:
            break
    return out


def reach(img, md, roots, depth=3):
    """roots (name -> [rva]) の起点ごとに direct call を depth 段まで独立に辿る。戻り値: rva -> (最浅深さ, 到達元 export 名の集合)。
    起点集合は子へ伝播させる必要があるため、起点を変えて全体を再訪する (BFS は起点ごと)。"""
    calls = {}
    seen = {}
    for name, vs in roots.items():
        visited = set()
        frontier = set(vs)
        for d in range(depth + 1):
            nxt = set()
            for f in frontier - visited:
                visited.add(f)
                if f not in seen:
                    seen[f] = [d, set()]
                seen[f][0] = min(seen[f][0], d)
                seen[f][1].add(name)
                if d < depth:
                    if f not in calls:
                        calls[f] = direct_calls(img, md, f)
                    nxt.update(calls[f])
            frontier = nxt
    return {f: (d, org) for f, (d, org) in seen.items()}


def negative_control(elq, dsp, md, rows_entries):
    """dsp の pdata 関数のうち IPPCODE 着地点でも export 表の variant でもない関数 (非 IPP 本体) を、
    入口の完全一致照合にかけ、偶然一致の数を数える (期待 0 付近)。"""
    ents = {e: sha(tokens(elq, md, e)) for e in rows_entries}
    ent_set = set(ents.values())
    hits_all = set(rel_targets(dsp, md))
    pool = [b.struct.BeginAddress for b in getattr(dsp['pe'], 'DIRECTORY_ENTRY_EXCEPTION', [])
            if dsp['text_lo'] <= b.struct.BeginAddress < dsp['text_hi']
            and b.struct.BeginAddress not in hits_all][:3000]
    n_hit = 0
    for f in pool:
        if sha(tokens(dsp, md, f)) in ent_set:
            n_hit += 1
    return {'pool_non_ipp_dsp_functions': len(pool), 'exact_matches_with_entries': n_hit}


def sha(toks):
    return hashlib.sha1('\n'.join(toks).encode()).hexdigest()


def bigrams(toks):
    return {(toks[i], toks[i + 1]) for i in range(len(toks) - 1)}


def indirect_scan(elq, md, entries):
    """.text の lea rip 相対 IPPCODE 参照、間接 call/jmp、.rdata/.data の IPPCODE 向きポインタを数える。"""
    base = elq['base']
    lea_targets = collections.Counter()
    ind_sites = []
    imm_ipp = []

    def on(rva, ins):
        if ins.mnemonic == 'lea' and 'rip' in ins.op_str:
            t = rva + ins.size + int.from_bytes(ins.bytes[-4:], 'little', signed=True)
            if elq['ipp_lo'] <= t < elq['ipp_hi']:
                lea_targets[t] += 1
        if ins.mnemonic in ('call', 'jmp') and not ins.op_str.startswith('0x'):
            ind_sites.append((rva, ins.mnemonic, ins.op_str))
        if not ins.mnemonic.startswith('j') and ins.mnemonic != 'call':
            for h in re.findall(r'0x[0-9a-f]{6,}', ins.op_str):
                v = int(h, 16) - base
                if elq['ipp_lo'] <= v < elq['ipp_hi']:
                    imm_ipp.append((rva, ins.op_str))
    sweep(elq, md, on)
    data_ptrs = set()
    for n in ('.rdata', '.data', '.pdata', '_RDATA', 'IPPDATA'):
        s = elq['secs'].get(n)
        if s is None:
            continue
        lo = s.VirtualAddress
        raw = elq['mem'][lo:lo + s.Misc_VirtualSize]
        for off in range(0, len(raw) - 7, 8):
            v = int.from_bytes(raw[off:off + 8], 'little') - base
            if elq['ipp_lo'] <= v < elq['ipp_hi']:
                data_ptrs.add(v)
    return lea_targets, ind_sites, data_ptrs, imm_ipp


def write_csv(rows):
    mat_path = os.path.join(HERE, '..', '..', 'ipp', 'data', 'ipp_matrix.csv')
    poc = {r['name']: r['implemented_poc'] == '1' for r in csv.DictReader(open(mat_path))}
    out = os.path.join(HERE, 'data', 'entries.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['entry_va', 'class', 'names', 'origin_exports', 'tools_ipp_poc', 'insns', 'call_sites',
                    'dsp_rva', 'dsp_depth', 'ratio'])
        for r in rows:
            named = r['class'] in ('identified', 'family_candidates')
            names = r['export_names'] if named else []
            impl = ''
            if names:
                impl = 'impl' if all(poc.get(n) for n in names) else (
                    'stub_only' if not any(poc.get(n) for n in names) else 'mixed')
            w.writerow([hex(r['entry_va']), r['class'], '|'.join(names), '|'.join(r['export_names']), impl,
                        r['tokens'], r['call_sites'], '|'.join(r['dsp_rva'][:2]),
                        r['dsp_depth'][0] if r['dsp_depth'] else '',
                        r['ratio'] if r['ratio'] is not None else ''])


def main():
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    elq = load(ELQ)
    dsp = load(DSP)
    print(f'elastique: {ELQ} IPPCODE RVA {elq["ipp_lo"]:#x}-{elq["ipp_hi"]:#x}')
    print(f'dsp_ippv2: {DSP} IPPCODE RVA {dsp["ipp_lo"]:#x}-{dsp["ipp_hi"]:#x}')

    hits = rel_targets(elq, md)
    entries = sorted(hits)
    n_sites = sum(len(v) for v in hits.values())
    fns = [(e.struct.BeginAddress, e.struct.EndAddress) for e in getattr(elq['pe'], 'DIRECTORY_ENTRY_EXCEPTION', [])
           if elq['text_lo'] <= e.struct.BeginAddress < elq['text_hi']]
    n_pdata_callers = sum(1 for e in entries if any(
        any(b <= s < en for b, en in fns) for s in hits[e]))
    print(f'linear-sweep entries (distinct call/jmp targets in IPPCODE): {len(entries)} (call/jmp sites {n_sites})')
    print(f'pdata (.text 関数) 件数: {len(fns)}; 入口のうち呼出元が pdata 関数内にあるもの: {n_pdata_callers}')

    exports = [(s.name.decode(), s.address) for s in dsp['pe'].DIRECTORY_ENTRY_EXPORT.symbols if s.name]
    variant_names = collections.defaultdict(set)
    exp_tables = {}
    for name, rva in exports:
        vs = dispatch_table(dsp, md, rva)
        exp_tables[name] = vs
        for v in vs:
            variant_names[v].add(name)
    sizes = collections.Counter(len(v) for v in exp_tables.values())
    print(f'dsp export {len(exports)}: variant 数の分布 (表の項数) {dict(sorted(sizes.items()))}')

    roots = collections.defaultdict(list)
    for name, vs in exp_tables.items():
        roots[name] = vs
    reached = reach(dsp, md, roots, depth=REACH_DEPTH)
    dsp_hits = rel_targets(dsp, md)
    origin = collections.defaultdict(set)
    depth_of = {}
    for f, (d, org) in reached.items():
        origin[f] |= org
        depth_of[f] = d
    for f in dsp_hits:
        origin.setdefault(f, set())
        depth_of.setdefault(f, -1)
    dsp_tok = {}
    by_sig = collections.defaultdict(list)
    for f in origin:
        dsp_tok[f] = tokens(dsp, md, f)
        by_sig[sha(dsp_tok[f])].append(f)
    print(f'dsp 候補本体: export 表の variant {len(variant_names)} 個 / export から call で {REACH_DEPTH} 段内 {len(reached)} 個 / dsp .text 由来の IPPCODE 着地点 {len(dsp_hits)} 個 → 照合対象 {len(origin)} 個')

    ent_info = {}
    for e in entries:
        ent_info[e] = {'raw_tok': tokens(elq, md, e)}
        f, chain = follow(elq, md, e)
        ent_info[e].update(final=f, hops=len(chain) - 1, fin_tok=tokens(elq, md, f))

    # bigram 索引 (近似候補の絞り込み用)
    vbg = {v: bigrams(t) for v, t in dsp_tok.items()}
    variant_set = set(variant_names)
    rows = []
    for e in entries:
        info = ent_info[e]
        kind, cand = None, []
        for label, tok in (('exact_final', info['fin_tok']), ('exact_raw', info['raw_tok'])):
            if by_sig.get(sha(tok)):
                kind, cand = label, by_sig[sha(tok)]
                break
        ratio = None
        if kind is None:
            eb = bigrams(info['fin_tok'])
            scored = sorted(((len(eb & vbg[v]) / max(1, len(eb | vbg[v])), v) for v in vbg), reverse=True)[:5]
            best = None
            for _, v in scored:
                r = difflib.SequenceMatcher(None, info['fin_tok'], dsp_tok[v], autojunk=False).ratio()
                if best is None or r > best[0]:
                    best = (r, v)
            if best:
                ratio, bv = best
                kind, cand = 'fuzzy_only', [bv]
        names = sorted({n for v in cand for n in origin.get(v, ())}) if kind and kind.startswith('exact') else []
        ntok = len(info['fin_tok'])
        if kind is None or kind == 'fuzzy_only':
            cls = 'unidentified_no_exact'
        elif ntok < TRIVIAL:
            cls = 'trivial_body'
        elif not names:
            cls = 'exact_dsp_internal_no_export'
        elif len(names) == 1:
            cls = 'identified'
        else:
            cls = 'family_candidates'
        rows.append({'entry_va': elq['base'] + e, 'entry_rva': e, 'final_rva': info['final'],
                     'thunk_hops': info['hops'], 'call_sites': len(hits[e]),
                     'match': kind or 'none', 'ratio': round(ratio, 4) if ratio is not None else None,
                     'dsp_rva': [hex(c) for c in cand][:4], 'export_names': names,
                     'dsp_is_export_variant': any(c in variant_set for c in cand),
                     'dsp_depth': [depth_of.get(c) for c in cand][:4],
                     'tokens': len(info['fin_tok']), 'class': cls})

    cnt = collections.Counter(r['match'] for r in rows)
    print(f'照合: {dict(cnt)}')
    print(f'区分: {dict(collections.Counter(r["class"] for r in rows))}')

    lea_t, ind, data_ptrs, imm_ipp = indirect_scan(elq, md, entries)
    ind_pat = collections.Counter(re.sub(r'\s+', ' ', o) if 'r10 + rax*8' not in o else 'table[r10+rax*8]' for _, _, o in ind)
    print(f'間接 call/jmp の形: {dict(ind_pat.most_common(12))}')
    print(f'即値・変位に IPPCODE 番地を含む命令: {len(imm_ipp)}')
    neg = negative_control(elq, dsp, md, rows_entries=entries)
    eset = set(entries)
    print(f'lea rip で IPPCODE を指す箇所: {sum(lea_t.values())} 箇所 / {len(lea_t)} 着地点 (うち入口 {len(eset & set(lea_t))})')
    print(f'間接 call/jmp (.text): {len(ind)} 箇所 (例 {ind[:3]})')
    print(f'.rdata/.data の IPPCODE 向きポインタ: {len(data_ptrs)} (うち入口 {len(eset & data_ptrs)}、入口外 {len(data_ptrs - eset)})')

    write_csv(rows)
    os.makedirs(WORK, exist_ok=True)
    json.dump({'elastique': os.path.basename(ELQ), 'dsp': os.path.basename(DSP),
               'entry_count': len(rows), 'entry_addresses': [r['entry_va'] for r in rows],
               'call_jmp_sites': n_sites, 'pdata_text_functions': len(fns),
               'pdata_callers_of_entries': n_pdata_callers,
               'lea_rip_ipp_targets': {hex(elq['base'] + k): v for k, v in lea_t.items()},
               'indirect_sites': [(hex(elq['base'] + a), m, o) for a, m, o in ind],
               'data_ptrs_ipp': sorted(hex(elq['base'] + d) for d in data_ptrs),
               'data_ptrs_ipp_not_entry': sorted(hex(elq['base'] + d) for d in data_ptrs - eset),
               'imm_ipp_sites': len(imm_ipp), 'indirect_pattern': dict(ind_pat),
               'negative_control': neg,
               'rows': rows}, open(os.path.join(WORK, 'facts.json'), 'w'), indent=1)


if __name__ == '__main__':
    sys.exit(main())
