#!/usr/bin/env python3
"""khbase_classify.py — KH-4: 共通基盤 (infra) 関数の (a)(b)(c) 分類を実測データから確定する。

infra  = 事前解析 (tools/targets/kilohearts/work/closures_sets.pkl) の「≥8 snap-in が DSP root から到達」188 関数
(a)    = infra ∪ á path の direct-call closure (既存 10 snap-in の process VA 起点) — lift 対象
         ※ lift 済み (snapins.json の lift セット) / 未 lift (stub 宣言 or 未接続) を併記
(b)    = infra − (a) のうち Editor/EditorModel/Controller vtable root から到達 (UI・エディタ側 / model ライフサイクル)
(c)    = infra − (a) − (b) — 未到達 (残り 32 snap-in の lift 時に到達見込み, Tier-M 引継)

root データ: work/callgraph.pkl (全域 sweep の直接 call/jmp 辺 — 間接 call は未追跡 = 下限)
実績データ: snapins.json の lift セット + work/<snap>/s0/lowered.ll.json の unlifted_callees (stub 宣言)
usage: khbase_classify.py [--json OUT]  (表を stdout, 詳細 JSON を --json へ)
"""
import argparse
import json
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KH = os.path.normpath(os.path.join(HERE, '..', '..'))           # tools/targets/kilohearts
SNAP = os.path.dirname(HERE)
BASE = 0x180000000
LIFTED10 = ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq', 'resonator', 'stereo', 'disperser', 'formant']


def reach(res, roots):
    seen, st = set(), list(roots)
    while st:
        f = st.pop()
        if f in seen or f not in res:
            continue
        seen.add(f)
        st.extend(res[f]['calls'])
        st.extend(res[f]['jmps'])
    return seen


def roots_of(vt, ns, pat):
    """クラス名末尾が pat (正規表現 $ 付きで一致) の vtable slot 全部 (RVA)"""
    import re
    out = []
    for k, lst in vt.items():
        rest = k[4:]
        rest = rest[:-2] if rest.endswith('@@') else rest
        if '?' in rest or '$' in rest:
            continue
        parts = [p for p in rest.split('@') if p]
        if len(parts) != 2 or parts[1] != ns:
            continue
        if re.search(pat, parts[0]):
            for v in lst:
                out += [int(s, 16) - BASE for s in v['slots']]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=None)
    a = ap.parse_args()

    cs = pickle.load(open(os.path.join(KH, 'work', 'closures_sets.pkl'), 'rb'))
    infra = sorted(cs['infra'])
    cg = pickle.load(open(os.path.join(KH, 'work', 'callgraph.pkl'), 'rb'))
    res, base = cg['res'], cg['base']
    assert base == BASE
    vt = json.load(open(os.path.join(KH, 'work', 'rtti_vtables.json')))
    cfg = json.load(open(os.path.join(SNAP, 'snapins.json')))

    # ---- 10 snap-in の process 起点 closure (実績: ctx-fuzz 200+1000 検証済みの lift 経路)
    proc_va = {}
    for n in LIFTED10:
        proc_va[n] = int(cfg[n]['lift']['proc'], 16) - BASE
    proc_clos = {n: reach(res, [proc_va[n]]) for n in LIFTED10}

    # ---- lift セット (実績: lift+検証済み) と stub 宣言 (静的に call されるが未 lift)
    lifted_rva, stub_rva = {}, {}
    for n in LIFTED10:
        lifted_rva[n] = {int(v, 16) - BASE for v in cfg[n]['lift'].values()}
        p = os.path.join(SNAP, 'work', n, 's0', 'lowered.ll.json')
        stub_rva[n] = set()
        if os.path.exists(p):
            stub_rva[n] = {int(x, 16) - BASE for x in json.load(open(p)).get('unlifted_callees', [])}

    union_proc = set().union(*proc_clos.values())
    union_lift = set().union(*lifted_rva.values())
    union_stub = set().union(*stub_rva.values())

    # ---- editor 側 root (42 効果全体; (b) 判定用)
    editor_reach = set()
    dsp_reach = set()
    NS42 = [ns for ns in cfg and json.load(open(os.path.join(KH, 'work', 'closures.json')))['ns']]
    for ns in NS42:
        er = reach(res, roots_of(vt, ns, r'(Editor|EditorModel|Controller)$'))
        dr = reach(res, roots_of(vt, ns, r'(MasterDsp|Dsp|DspModel)$'))
        editor_reach |= er
        dsp_reach |= dr

    rows = []
    for f in infra:
        via = [n for n in LIFTED10 if f in proc_clos[n]]
        lifted_in = [n for n in LIFTED10 if f in lifted_rva[n]]
        stub_in = [n for n in LIFTED10 if f in stub_rva[n]]
        if via or f in union_lift or f in union_stub:
            cat = 'a'
        elif f in editor_reach:
            cat = 'b'
        else:
            cat = 'c'
        r = res.get(f, {})
        rows.append(dict(
            va=BASE + f, size=r.get('size', 0), cat=cat,
            via=via, lifted=lifted_in, stub=stub_in,
            editor=(f in editor_reach), dsp_root=(f in dsp_reach),
            fma=r.get('simd', {}).get('fma', 0), avx128=r.get('simd', {}).get('avx128', 0),
            iat=r.get('iat', 0), indir=r.get('indir', 0)))

    ncat = {k: sum(1 for r in rows if r['cat'] == k) for k in 'abc'}
    bcat = {k: sum(r['size'] for r in rows if r['cat'] == k) for k in 'abc'}
    print('infra total: %d funcs / %d B' % (len(rows), sum(r['size'] for r in rows)))
    print('(a) process 到達: %d funcs / %d B  (lift済 %d / 未lift %d)' % (
        ncat['a'], bcat['a'],
        sum(1 for r in rows if r['cat'] == 'a' and r['lifted']),
        sum(1 for r in rows if r['cat'] == 'a' and not r['lifted'])))
    print('(b) editor 到達のみ: %d funcs / %d B' % (ncat['b'], bcat['b']))
    print('(c) 未到達: %d funcs / %d B' % (ncat['c'], bcat['c']))

    if a.json:
        json.dump({'rows': rows, 'counts': ncat, 'bytes': bcat}, open(a.json, 'w'), indent=1)
        print('json ->', a.json)

    # ---- (a) 未 lift 一覧 (新規 lift 候補)
    newa = [r for r in rows if r['cat'] == 'a' and not r['lifted']]
    print('\n== (a) 未 lift (新規 lift 候補) %d 関数 / %d B ==' % (len(newa), sum(r['size'] for r in newa)))
    for r in sorted(newa, key=lambda r: -r['size']):
        print('  0x%x  %5dB  fma=%d avx128=%d iat=%d indir=%d  via=%s stub=%s' % (
            r['va'], r['size'], r['fma'], r['avx128'], r['iat'], r['indir'],
            ','.join(n[:4] for n in r['via']) or '-', ','.join(n[:4] for n in r['stub']) or '-'))


if __name__ == '__main__':
    main()
