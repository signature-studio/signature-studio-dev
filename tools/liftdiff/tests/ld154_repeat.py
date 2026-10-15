"""同じ入力の batch を 2 回実行したときの判定の再現性を測る (LD-154 / #3350)。

使い方: python3 tests/ld154_repeat.py A.jsonl B.jsonl [--tsv out.tsv]
出力: 各 run の verdict 件数と timing (timeout/hang/crash) の件数・経過秒、A と B の判定変化、
      変化した関数ごとに「判定が変わった case」と、その case (または関数内の case) に timing が付いていたか。
判定ロジックは見ず、batch JSONL の verdict と cases だけを突き合わせる。
"""
import collections
import json
import sys


def load(path):
    d = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                d[r['function']['va']] = r
    return d


def case_key(c):
    return c['pattern'] + ('#%s' % c['fvm_arg'] if 'fvm_arg' in c else '')


def cases_of(r):
    return {case_key(c): c for c in r.get('cases', [])}


def timed(c):
    return c is not None and ('timing' in c or 'refine_timing' in c)


def describe(c):
    if c is None:
        return '-'
    return '%s/%s/%s' % (c['outcome'], c.get('native_status'), c.get('wasm_status'))


def timing_summary(d):
    """timing を持つ case の (side, status) 件数と、side ごとの実測秒の範囲。"""
    cnt = collections.Counter()
    el = collections.defaultdict(list)
    for r in d.values():
        for c in r.get('cases', []):
            t = c.get('timing')
            if not t:
                continue
            for side in ('native', 'wasm'):
                s = t[side]['status']
                cnt[(side, s)] += 1
                if s in ('timeout', 'hang', 'crash') and t[side]['elapsed_s'] is not None:
                    el[(side, s)].append(t[side]['elapsed_s'])
    return cnt, el


def pair(a_path, b_path, rows):
    a, b = load(a_path), load(b_path)
    print('== A=%s  B=%s' % (a_path, b_path))
    for label, d in (('A', a), ('B', b)):
        S = collections.Counter(r['verdict'] for r in d.values())
        print('  %s: 一致 %d / 不一致 %d / 実行不能 %d (関数 %d)' % (label, S['match'], S['mismatch'], S['unexec'], len(d)))
        cnt, el = timing_summary(d)
        fn = sum(1 for r in d.values() if any(c.get('timing') for c in r.get('cases', [])))
        print('  %s: timing 付き case %d (関数 %d)' % (label, sum(v for (s, _), v in cnt.items() if s == 'native'), fn))
        for k in sorted(cnt):
            if k[1] != 'ok':
                e = el.get(k, [])
                rng = '%.3f..%.3f s' % (min(e), max(e)) if e else '-'
                print('      %-6s %-8s %5d  elapsed %s' % (k[0], k[1], cnt[k], rng))
    vas = sorted(set(a) | set(b))
    trans = collections.Counter()
    changed = []
    for va in vas:
        ra, rb = a.get(va), b.get(va)
        va_v = ra['verdict'] if ra else 'missing'
        vb_v = rb['verdict'] if rb else 'missing'
        if va_v != vb_v:
            trans[(va_v, vb_v)] += 1
            changed.append(va)
    print('  verdict 変化: %d 関数' % len(changed))
    for (x, y), n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print('    %s -> %s : %d' % (x, y, n))
    inv_diff = 0
    for va in changed:
        ra, rb = a.get(va), b.get(va)
        ca, cb = (cases_of(ra) if ra else {}), (cases_of(rb) if rb else {})
        diff_keys = [k for k in sorted(set(ca) | set(cb)) if (ca.get(k) or {}).get('outcome') != (cb.get(k) or {}).get('outcome')
                     or (ca.get(k) or {}).get('native_status') != (cb.get(k) or {}).get('native_status')
                     or (ca.get(k) or {}).get('wasm_status') != (cb.get(k) or {}).get('wasm_status')]
        t_diff = any(timed(ca.get(k)) or timed(cb.get(k)) for k in diff_keys)
        t_fn = any(timed(c) for c in list(ca.values()) + list(cb.values()))
        inv_diff += t_diff
        va_v = ra['verdict'] if ra else 'missing'
        vb_v = rb['verdict'] if rb else 'missing'
        for k in diff_keys[:4] or ['(case 差なし)']:
            print('    %s %s->%s case %-8s A=%-28s B=%-28s timing(A/B)=%s/%s' % (
                va, va_v, vb_v, k, describe(ca.get(k)), describe(cb.get(k)),
                'Y' if timed(ca.get(k)) else '-', 'Y' if timed(cb.get(k)) else '-'))
        rows.append((a_path, b_path, va, va_v, vb_v, ','.join(diff_keys), 'Y' if t_diff else '-', 'Y' if t_fn else '-'))
    print('  判定変化の関数 %d のうち、差の出た case に timing が付いていた関数: %d' % (len(changed), inv_diff))
    print('')


def main():
    args = sys.argv[1:]
    tsv = None
    if '--tsv' in args:
        i = args.index('--tsv')
        tsv = args[i + 1]
        del args[i:i + 2]
    rows = []
    for i in range(0, len(args) - 1, 2):
        pair(args[i], args[i + 1], rows)
    if tsv:
        with open(tsv, 'w') as f:
            f.write('A\tB\tva\tverdict_A\tverdict_B\tdiff_cases\ttimed_diff_case\ttimed_in_fn\n')
            for r in rows:
                f.write('\t'.join(r) + '\n')


if __name__ == '__main__':
    main()
