#!/usr/bin/env python3
"""PLG-F2-3 (#515): leaf_diff.sh の liftdiff 出力 (work/f2/leaf/<block>.jsonl) を関数単位・case 単位に集計する。

  python3 tools/plugins/f2/leaf_report.py [--dir work/f2/leaf] [--md out.md] [--json out.json]

採点の定義 (liftdiff docs/FORMAT.md §3 と同一):
  関数 verdict   match    = native が完走した case が 1 以上あり、完走した全 case で 戻り値/書換えメモリ/import 呼出列/関数 entry 列 が一致
                 mismatch = 完走 case のどれかに差分、または native 完走 / wasm trap
                 unexec   = native が完走する case が 0 (比較不能)
  case outcome   equal / diff / wasm_trap (= native 完走 case)、native_fault / both_fault / hang (= 比較不能 case)
  1 関数 = 9 case (引数パターン z,s,p0,p1,p01,pall,pall2,q0,qall; tools/liftdiff/ldlib/cases.py)
"""
import collections, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work', 'f2')


def load(d):
    recs = []
    for p in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
        recs += [json.loads(l) for l in open(p) if l.strip()]
    return recs


def summarize(recs, meta):
    rows = []
    for r in recs:
        va = r['function']['va']
        m = meta.get((r['target'], va)) or {}
        cs = r.get('cases', [])
        oc = collections.Counter(c['outcome'] for c in cs)
        mach = (r.get('static') or {}).get('machine') or {}
        sig = r['function'].get('sig') or {}
        rows.append({
            'target': r['target'], 'block': m.get('block'), 'plugin': m.get('plugin'), 'va': va,
            'bytes': m.get('bytes'), 'sig': '%s(%s)' % (sig.get('ret'), ','.join(sig.get('params', []))),
            'verdict': r['verdict'], 'unexec_reason': r.get('unexec_reason'),
            'cases': len(cs), 'equal': oc['equal'], 'diff': oc['diff'], 'wasm_trap': oc['wasm_trap'],
            'not_comparable': sum(oc[k] for k in ('native_fault', 'both_fault', 'hang')),
            'native_ok': sum(1 for c in cs if c.get('native_status') == 'ok'),
            'tags': [t['tag'] for t in r.get('tags', [])],
            'leaf_self_diff': any(c.get('leaf') and c['outcome'] == 'diff' for c in cs),
            'ins': mach.get('ins'), 'fpcmp': mach.get('fpcmp'), 'ijmp': mach.get('ijmp'), 'icall': mach.get('icall'),
            'arity_x': mach.get('arity_x'), 'arity_gpr': mach.get('arity_gpr'), 'stack_args': mach.get('stack_args'),
            'ir_params': len(sig.get('params', [])),
        })
    return rows


def main():
    a = sys.argv[1:]
    d, md, js = os.path.join(W, 'leaf'), None, None
    while a:
        if a[0] == '--dir':
            d, a = a[1], a[2:]
        elif a[0] == '--md':
            md, a = a[1], a[2:]
        elif a[0] == '--json':
            js, a = a[1], a[2:]
        else:
            raise SystemExit('unknown arg ' + a[0])
    meta = {}
    for r in json.load(open(os.path.join(W, 'leaf.json'))):
        meta[('eqf%d' % r['block'], r['va'])] = r
    recs = load(d)
    rows = summarize(recs, meta)
    rows.sort(key=lambda r: (r['block'] or 0, int(r['va'], 16)))
    L = []
    L.append('| # | block | plugin | VA | 機械語 B | IR 署名 | verdict | equal/native完走/全 case | 機械語 xmm 引数 | 機械語 jmp reg | タグ |')
    L.append('|--:|--:|---|---|--:|---|---|---|--:|--:|---|')
    for i, r in enumerate(rows, 1):
        L.append('| %d | %s | %s | %s | %s | `%s` | **%s**%s | %d/%d/%d | %s | %s | %s |' % (
            i, r['block'], r['plugin'], r['va'], r['bytes'], r['sig'], r['verdict'],
            (' (%s)' % r['unexec_reason']) if r['unexec_reason'] else '', r['equal'], r['native_ok'], r['cases'],
            r['arity_x'], r['ijmp'], ','.join(r['tags']) or '-'))
    V = collections.Counter(r['verdict'] for r in rows)
    tot = collections.Counter()
    for r in rows:
        for k in ('cases', 'equal', 'diff', 'wasm_trap', 'not_comparable', 'native_ok'):
            tot[k] += r[k]
    tags = collections.Counter(t for r in rows for t in r['tags'])
    L.append('')
    L.append('関数 %d: **一致 %d / 不一致 %d / 実行不能 %d**' % (len(rows), V['match'], V['mismatch'], V['unexec']))
    L.append('case %d: native 完走 %d (equal %d / diff %d / wasm_trap %d)、比較不能 %d (native_fault/both_fault/hang)' % (
        tot['cases'], tot['native_ok'], tot['equal'], tot['diff'], tot['wasm_trap'], tot['not_comparable']))
    L.append('不一致タグ (該当関数数): ' + (', '.join('%s %d' % kv for kv in tags.most_common()) or 'なし'))
    L.append('不一致のうち callee 無しで差分 (自己欠陥確定): %d' % sum(1 for r in rows if r['verdict'] == 'mismatch' and r['leaf_self_diff']))
    out = '\n'.join(L)
    print(out)
    if md:
        open(md, 'w').write(out + '\n')
    if js:
        json.dump({'functions': rows, 'verdict': V, 'cases': tot}, open(js, 'w'), indent=1)


if __name__ == '__main__':
    main()
