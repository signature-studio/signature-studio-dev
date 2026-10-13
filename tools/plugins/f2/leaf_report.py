#!/usr/bin/env python3
"""PLG-F2-3 (#515): leaf_diff.sh (主採点) と leaf_custom.py (補助採点) の liftdiff 出力を関数単位・case 単位に集計する。

  python3 tools/plugins/f2/leaf_report.py [--dir work/f2/leaf] [--cdir work/f2/leaf_custom] [--md out.md] [--json out.json]

採点の定義 (liftdiff docs/FORMAT.md §3 と同一):
  関数 verdict   match    = native が完走した case が 1 以上あり、完走した全 case で 戻り値/書換えメモリ/import 呼出列/関数 entry 列 が一致
                 mismatch = 完走 case のどれかに差分、または native 完走 / wasm trap
                 unexec   = native が完走する case が 0 (比較不能)
  case outcome   equal / diff / wasm_trap (= native 完走 case)、native_fault / both_fault / hang (= 比較不能 case)
  主採点   : 1 関数 = 9 case (引数パターン z,s,p0,p1,p01,pall,pall2,q0,qall; tools/liftdiff/ldlib/cases.py)
  補助採点 : 主採点が unexec / 時間切れ / 比較系の偽陽性になった関数に、引数の意味に合わせた手作り case (leaf_custom.py) を足したもの
最終判定 (関数ごと 1 つ):
  補助 case が無い                          -> 主採点の verdict
  補助が mismatch                           -> mismatch (主採点が match でも。 主採点の match は検出力不足だった)
  補助が match かつ 主採点が match/unexec   -> match
  補助が match かつ 主採点が mismatch       -> leaf_custom.ARTIFACT に根拠がある (比較系の偽陽性と確定済み) ときだけ match、無ければ mismatch
  補助が unexec                             -> 主採点の verdict
"""
import collections, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work', 'f2')
sys.path.insert(0, HERE)


def load(d):
    recs = []
    for p in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
        recs += [json.loads(l) for l in open(p) if l.strip()]
    return recs


def stat(r):
    cs = r.get('cases', [])
    oc = collections.Counter(c['outcome'] for c in cs)
    return {'verdict': r['verdict'], 'unexec_reason': r.get('unexec_reason'), 'cases': len(cs), 'equal': oc['equal'], 'diff': oc['diff'],
            'wasm_trap': oc['wasm_trap'], 'not_comparable': sum(oc[k] for k in ('native_fault', 'both_fault', 'hang')),
            'native_ok': sum(1 for c in cs if c.get('native_status') == 'ok'),
            'tags': [t['tag'] for t in r.get('tags', [])],
            'leaf_self_diff': any(c.get('leaf') and c['outcome'] == 'diff' for c in cs)}


def final(prim, cust, artifact):
    if not cust or cust['verdict'] == 'unexec':
        return prim['verdict'], ''
    if cust['verdict'] == 'mismatch':
        return 'mismatch', ''
    if prim['verdict'] == 'mismatch':
        return ('match', 'ARTIFACT') if artifact else ('mismatch', '')
    return 'match', ''


def summarize(meta, artifact, d, cd):
    P = {(r['target'], int(r['function']['va'], 16)): r for r in load(d)}
    C = {(r['target'], int(r['function']['va'], 16)): r for r in load(cd)} if os.path.isdir(cd) else {}
    rows = []
    for (t, va), r in P.items():
        m = meta[(t, hex(va))]
        prim = stat(r)
        cust = stat(C[(t, va)]) if (t, va) in C else None
        fin, note = final(prim, cust, va in artifact)
        sig = r['function'].get('sig') or {}
        mach = (r.get('static') or {}).get('machine') or {}
        rows.append({'block': m['block'], 'plugin': m['plugin'], 'va': hex(va), 'bytes': m['bytes'],
                     'sig': '%s(%s)' % (sig.get('ret'), ','.join(sig.get('params', []))),
                     'primary': prim, 'custom': cust, 'final': fin, 'note': note,
                     'tags': sorted(set(prim['tags']) | set((cust or {}).get('tags', []))),
                     'arity_x': mach.get('arity_x'), 'ijmp': mach.get('ijmp'),
                     'artifact': artifact.get(va) if note else None})
    rows.sort(key=lambda r: (r['block'], int(r['va'], 16)))
    return rows


def main():
    a = sys.argv[1:]
    d, cd, md, js = os.path.join(W, 'leaf'), os.path.join(W, 'leaf_custom'), None, None
    while a:
        k, v, a = a[0], a[1], a[2:]
        if k == '--dir': d = v
        elif k == '--cdir': cd = v
        elif k == '--md': md = v
        elif k == '--json': js = v
        else: raise SystemExit('unknown arg ' + k)
    meta = {('eqf%d' % r['block'], r['va']): r for r in json.load(open(os.path.join(W, 'leaf.json')))}
    from leaf_custom import ARTIFACT
    rows = summarize(meta, ARTIFACT, d, cd)
    L = ['| # | block | plugin | VA | 機械語 B | IR 署名 | 主採点 (9 パターン) | 補助 case | **最終** | タグ |',
         '|--:|--:|---|---|--:|---|---|---|---|---|']
    for i, r in enumerate(rows, 1):
        p, c = r['primary'], r['custom']
        pv = '%s%s %d/%d/%d' % (p['verdict'], '(%s)' % p['unexec_reason'] if p['unexec_reason'] else '', p['equal'], p['native_ok'], p['cases'])
        cv = '%s %d/%d' % (c['verdict'], c['equal'], c['cases']) if c else '-'
        L.append('| %d | %s | %s | %s | %s | `%s` | %s | %s | **%s**%s | %s |' % (
            i, r['block'], r['plugin'], r['va'], r['bytes'], r['sig'], pv, cv, r['final'], ' (偽陽性確定)' if r['note'] else '', ','.join(r['tags']) or '-'))
    V = collections.Counter(r['final'] for r in rows)
    PV = collections.Counter(r['primary']['verdict'] for r in rows)
    tot, ctot = collections.Counter(), collections.Counter()
    for r in rows:
        for k in ('cases', 'equal', 'diff', 'wasm_trap', 'not_comparable', 'native_ok'):
            tot[k] += r['primary'][k]
            if r['custom']:
                ctot[k] += r['custom'][k]
    tags = collections.Counter(t for r in rows if r['final'] == 'mismatch' for t in r['tags'])
    L.append('')
    L.append('最終判定 %d 関数: **一致 %d / 不一致 %d / 実行不能 %d**' % (len(rows), V['match'], V['mismatch'], V['unexec']))
    L.append('主採点のみ: 一致 %d / 不一致 %d / 実行不能 %d。 case %d: native 完走 %d (equal %d / diff %d / wasm_trap %d)、比較不能 %d' % (
        PV['match'], PV['mismatch'], PV['unexec'], tot['cases'], tot['native_ok'], tot['equal'], tot['diff'], tot['wasm_trap'], tot['not_comparable']))
    L.append('補助採点 %d 関数: case %d (equal %d / diff %d / wasm_trap %d / 比較不能 %d)' % (
        sum(1 for r in rows if r['custom']), ctot['cases'], ctot['equal'], ctot['diff'], ctot['wasm_trap'], ctot['not_comparable']))
    L.append('最終 mismatch のタグ (該当関数数): ' + (', '.join('%s %d' % kv for kv in tags.most_common()) or 'なし'))
    L.append('最終 mismatch のうち callee 無しで差分 (自己欠陥確定): %d' % sum(
        1 for r in rows if r['final'] == 'mismatch' and (r['primary']['leaf_self_diff'] or (r['custom'] or {}).get('leaf_self_diff'))))
    L.append('比較に使った equal case 数が 3 未満の match (検出力弱): ' + (', '.join('%s(%d)' % (r['va'], r['primary']['equal'] + (r['custom'] or {'equal': 0})['equal'])
             for r in rows if r['final'] == 'match' and r['primary']['equal'] + (r['custom'] or {'equal': 0})['equal'] < 3) or 'なし'))
    out = '\n'.join(L)
    print(out)
    if md:
        open(md, 'w').write(out + '\n')
    if js:
        json.dump({'functions': rows, 'final': V, 'primary': PV}, open(js, 'w'), indent=1)


if __name__ == '__main__':
    main()
