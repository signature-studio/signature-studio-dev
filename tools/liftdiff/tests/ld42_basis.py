"""units と hybrid の sample 判定遷移について、関数ごとの差分根拠を表にする (LD-50 / #1464)。

使い方: python3 tests/ld42_basis.py <units.jsonl> <hybrid.jsonl> [--md out.md]
出力: 遷移 1 件 1 行の Markdown 表。units / hybrid の判定、主因タグ (DEFECTS の優先順位)、
pattern の outcome 内訳 (`cases` 全件。units 側は全 pattern が equal/diff/wasm_trap でない関数に fvm (LD-23) の case を追加するため、11 件を超える行がある)、根拠の区分。
根拠の区分は上から順に判定する: units の実行不能の解消 → hybrid の実行不能 → native 異常 → wasm trap → 両側実行の差分。
"""
import collections
import sys

from ld42_transition import load

PRIORITY = ['callee_divergence', 'wasm_trap', 'callsite_arg_drop', 'memory_semantics', 'icall_drop',
            'xmm_arg_drop', 'ret_only', 'import_arg_diff', 'simd_helper', 'zero_init_drop',
            'fp_flag_unreflected', 'spill_slot_deref', 'import_call_seq', 'unresolved_callee', 'arg_drop']
OUTCOMES = ['equal', 'diff', 'native_fault', 'both_fault', 'wasm_trap', 'hang', 'wasm_timeout_native_long']


def primary(r):
    if r is None:
        return '-'
    tags = set(t['tag'] if isinstance(t, dict) else str(t) for t in r.get('tags', []))
    for p in PRIORITY:
        if p in tags:
            return p
    return '-'


def outcome_counts(r):
    if r is None:
        return '-'
    c = collections.Counter(x['outcome'] for x in r.get('cases', []))
    parts = ['%s %d' % (k, c[k]) for k in OUTCOMES if c.get(k)]
    return ', '.join(parts) if parts else '-'


def verdict(r):
    if r is None:
        return 'missing'
    if r['verdict'] == 'unexec':
        return 'unexec (%s)' % r.get('unexec_reason', '?')
    return r['verdict']


def basis(u, h):
    if u is None or h is None:
        return 'データ欠落'
    if u['verdict'] == 'unexec' and h['verdict'] != 'unexec':
        return 'units は実行不能 (%s)。hybrid で実行可能になった' % u.get('unexec_reason', '?')
    if h['verdict'] == 'unexec':
        return 'hybrid は実行不能 (%s)' % h.get('unexec_reason', '?')
    if h['verdict'] == 'match':
        return 'hybrid で一致 (差分 0)'
    cases = h.get('cases', [])
    nat_bad = sum(1 for x in cases if x.get('native_status') not in ('ok', None))
    wasm_bad = sum(1 for x in cases if x.get('wasm_status') in ('trap', 'timeout', 'hang', 'crash'))
    if nat_bad * 2 >= len(cases):
        return 'hybrid: native 異常 %d/%d patterns' % (nat_bad, len(cases))
    if wasm_bad * 2 >= len(cases):
        return 'hybrid: wasm trap/timeout %d/%d patterns' % (wasm_bad, len(cases))
    return 'hybrid: 両側実行の差分 (主因 %s)' % primary(h)


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    md = sys.argv[sys.argv.index('--md') + 1] if '--md' in sys.argv else None
    a, b = load(a_path), load(b_path)
    rows = []
    for va in sorted(set(a) | set(b)):
        ra, rb = a.get(va), b.get(va)
        if verdict(ra).split(' ')[0] == verdict(rb).split(' ')[0]:
            continue
        name = (rb or ra)['function'].get('name', '')
        rows.append((va, name, ra, rb))
    lines = ['| # | va | 名前 | units → hybrid | units 主因 | hybrid 主因 | units の pattern 内訳 | hybrid の pattern 内訳 | 根拠 |',
             '|---|---|---|---|---|---|---|---|---|']
    for i, (va, name, ra, rb) in enumerate(rows, 1):
        lines.append('| %d | %s | %s | %s → %s | %s | %s | %s | %s | %s |' % (
            i, va, name, verdict(ra), verdict(rb), primary(ra), primary(rb),
            outcome_counts(ra), outcome_counts(rb), basis(ra, rb)))
    print('transitions %d' % len(rows))
    trans = collections.Counter((verdict(x[2]).split(' ')[0], verdict(x[3]).split(' ')[0]) for x in rows)
    for (x, y), n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print('  %s -> %s : %d' % (x, y, n))
    if md:
        with open(md, 'w') as f:
            f.write('\n'.join(lines) + '\n')
    else:
        print('\n'.join(lines))


if __name__ == '__main__':
    main()
