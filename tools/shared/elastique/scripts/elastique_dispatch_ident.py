#!/usr/bin/env python3
"""élastique の dispatch 層の飛び先 (1 段目 186・2 段目 251) に IPP API 名か「未同定」を付ける (T-SH-43 / #2667).

入力: tools/shared/work/elastique/dispatch.json (elastique_dispatch.py の出力)。
      ELASTIQUE_DLL・DSP_IPP_DLL (ipp_entries.py と同じ既定値・環境変数)。
出力: data/dispatch_targets.csv (コミット対象) と標準出力の集計。
照合は ipp_entries.py (#2613) と同じ方法: thunk を 4 段まで追い、正規化命令列の SHA-1 の完全一致だけを根拠にする。
近似比は使わない。IPPCODE 直接 call 先の同定 (entries.csv) は説明用の列で、根拠にしない。
"""
import collections
import csv
import json
import os
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(HERE, '..')
sys.path.insert(0, SHARED)
import ipp_entries as ie  # noqa: E402

DISPATCH = os.path.join(SHARED, '..', 'work', 'elastique', 'dispatch.json')
ENTRIES = os.path.join(SHARED, 'data', 'entries.csv')
OUT = os.path.join(SHARED, 'data', 'dispatch_targets.csv')
MATRIX = os.path.join(SHARED, '..', '..', 'ipp', 'data', 'ipp_matrix.csv')
STUB = 0x1803E71B0
IDX_WRITER = 0x1800010A0


def dsp_index(dsp, md):
    exports = [(s.name.decode(), s.address) for s in dsp['pe'].DIRECTORY_ENTRY_EXPORT.symbols if s.name]
    roots = {name: ie.dispatch_table(dsp, md, rva) for name, rva in exports}
    reached = ie.reach(dsp, md, roots, depth=ie.REACH_DEPTH)
    origin = collections.defaultdict(set)
    depth = {}
    for f, (d, org) in reached.items():
        origin[f] |= org
        depth[f] = d
    for f in ie.rel_targets(dsp, md):
        origin.setdefault(f, set())
        depth.setdefault(f, -1)
    by_sig = collections.defaultdict(list)
    for f in origin:
        by_sig[ie.sha(ie.tokens(dsp, md, f))].append(f)
    return origin, depth, by_sig


def classify(img, md, index, rva):
    origin, depth, by_sig = index
    f, chain = ie.follow(img, md, rva)
    fin = ie.tokens(img, md, f)
    raw = ie.tokens(img, md, rva)
    kind, cand = 'none', []
    for label, tok in (('exact_final', fin), ('exact_raw', raw)):
        if by_sig.get(ie.sha(tok)):
            kind, cand = label, by_sig[ie.sha(tok)]
            break
    names = sorted({n for v in cand for n in origin.get(v, ())}) if kind != 'none' else []
    if kind == 'none':
        cls = 'unidentified_no_exact'
    elif len(fin) < ie.TRIVIAL:
        cls = 'trivial_body'
    elif not names:
        cls = 'exact_dsp_internal_no_export'
    elif len(names) == 1:
        cls = 'identified'
    else:
        cls = 'family_candidates'
    return {'final': f, 'hops': len(chain) - 1, 'match': kind, 'class': cls, 'names': names,
            'dsp_rva': [hex(c) for c in cand][:4], 'dsp_depth': [depth.get(c) for c in cand][:4],
            'tokens': len(fin)}


def label_of(c):
    if c['class'] == 'identified':
        return c['names'][0]
    if c['class'] == 'family_candidates':
        return '族候補:' + '|'.join(c['names'])
    return '未同定'


def body_calls(img, md, lo, hi):
    """本体 [lo, hi) の直接 call/jmp の即値先 (絶対 VA) を返す。"""
    base = img['base']
    out = []
    for ins in md.disasm(img['mem'][lo - base:hi - base], lo):
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == CS_OP_IMM:
            out.append(ins.operands[0].imm)
    return out


def main():
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    elq = ie.load(ie.ELQ)
    dsp = ie.load(ie.DSP)
    base = elq['base']
    ipp_lo, ipp_hi = base + elq['ipp_lo'], base + elq['ipp_hi']
    d = json.load(open(DISPATCH))
    index = dsp_index(dsp, md)
    poc = {r['name']: r['implemented_poc'] == '1' for r in csv.DictReader(open(MATRIX))}
    entries = {r['entry_va']: r for r in csv.DictReader(open(ENTRIES))}

    rows = []
    for level, key in ((1, 'variant_targets'), (2, 'hop2_targets')):
        for va_s, rec in d[key].items():
            va = int(va_s, 16)
            c = classify(elq, md, index, va - base)
            calls = set(body_calls(elq, md, va, rec['end']))
            ipp_c = sorted(t for t in calls if ipp_lo <= t < ipp_hi)
            callee_names = set()
            for t in ipp_c:
                callee_names |= set(filter(None, entries.get(hex(t), {}).get('names', '').split('|')))
            guard_ok = not calls or (set(ipp_c) == calls and bool(set(c['names']) & callee_names))
            cls = c['class'] if guard_ok or c['class'] not in ('identified', 'family_candidates') else 'shape_only'
            c['class'] = cls
            impl = ''
            if c['names']:
                impl = 'impl' if all(poc.get(n) for n in c['names']) else (
                    'stub_only' if not any(poc.get(n) for n in c['names']) else 'mixed')
            rows.append({'target_va': va, 'level': level, 'section': rec['section'], 'pdata': rec['pdata'],
                         'direct_calls': len(calls), 'ipp_callees': '|'.join(hex(t) for t in ipp_c),
                         'ipp_callee_names': '|'.join(sorted(callee_names)),
                         'final_va': base + c['final'], 'thunk_hops': c['hops'], 'match': c['match'],
                         'class': cls, 'label': label_of(c), 'names': '|'.join(c['names']),
                         'impl': impl, 'dsp_rva': '|'.join(c['dsp_rva'][:2]),
                         'dsp_depth': c['dsp_depth'][0] if c['dsp_depth'] else '', 'tokens': c['tokens'],
                         'body_end': hex(rec['end'])})
    rows.sort(key=lambda r: (r['level'], r['target_va']))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            r['target_va'] = hex(r['target_va'])
            w.writerow(r)

    for lv in (1, 2):
        sub = [r for r in rows if r['level'] == lv]
        print(f'level {lv}: {len(sub)} 件 / distinct {len({r["target_va"] for r in sub})}')
        print('  class:', dict(collections.Counter(r['class'] for r in sub)))
        print('  IPPCODE 直接 call 先あり:', sum(1 for r in sub if r['ipp_callees']))
        print('  label 一意名:', dict(collections.Counter(r['names'] for r in sub if r['class'] == 'identified')))
        print('  impl:', dict(collections.Counter(r['impl'] for r in sub if r['names'])))

    named = [r for r in rows if r['class'] in ('identified', 'family_candidates')]
    print('名付け (identified+family) 合計:', len(named))
    print('  一意名の distinct API:', sorted({r['names'] for r in rows if r['class'] == 'identified'}))
    print('  族候補の名前集合 distinct:', sorted({r['names'] for r in rows if r['class'] == 'family_candidates'}))

    # 位置づけ: 197 入口との比較 (説明用)
    ent_names = set()
    for r in entries.values():
        if r['names']:
            ent_names.update(r['names'].split('|'))
    disp_names = {n for r in named for n in r['names'].split('|')}
    print('197 入口の名前 distinct:', len(ent_names), '/ dispatch 側の名前 distinct:', len(disp_names),
          '/ 重なり:', sorted(ent_names & disp_names))

    # 初期化スタブ・索引書込み関数 (説明対象。根拠は同じ照合)
    pos = classify(elq, md, index, 0x1802F8DB0 - base)
    print('陽性対照 0x1802f8db0 (#2613 の一意名):', pos['class'], pos['names'])
    for name, va, size in (('stub 0x1803e71b0', STUB, 0x40), ('idx writer 0x1800010a0', IDX_WRITER, 0x80)):
        c = classify(elq, md, index, va - base)
        callees = [hex(t) for t in sorted(set(body_calls(elq, md, va, va + size)))]
        print(name, c['class'], c['names'], c['match'], 'callees', callees)

    outward = d['linear_out_list']
    print('IPPCODE 線形外向き:', len(outward), collections.Counter(x['tgt_section'] for x in outward))
    print('  .text 向き:', [x for x in outward if x['tgt_section'] == '.text'])

    # 0x1802f8030 (0x180001120 の callee・index 値域の確認)
    lo = 0x1802F8030
    ins_list = []
    for ins in md.disasm(elq['mem'][lo - base:lo - base + 64], lo):
        ins_list.append(f'{hex(ins.address)} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic == 'ret' or len(ins_list) >= 12:
            break
    print('0x1802f8030 body:', ins_list)


if __name__ == '__main__':
    sys.exit(main())
