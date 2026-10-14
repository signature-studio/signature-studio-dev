#!/usr/bin/env python3
"""LD-96 (#2258): ld96_heap_audit.py の出力 (work/ld96/{solo,p0,p1}.jsonl) を TSV に集計する。

  python3 ld96_summarize.py
    -> results/ld96_heap_residue.tsv         関数ごと (run = solo / chunk0 / chunk1 / control)
    -> results/ld96_heap_residue_summary.tsv run × side (native / wasm) ごとの件数・最小・最大

  n = 高水位より外に残った非 0 バイト数。z = 先頭 case (pattern z)。max = 監査した全 case の最大。
  control = 対照 (audit=2 の関数。既知の 1 B を計数の直前に置く)。solo の集計から外し、run 名を control にする。
  手順は REPORT_APPENDIX_LD96.md §8.7。
"""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work', 'ld96')
RESULTS = os.path.join(HERE, 'results')
RUNS = [('solo', 'solo.jsonl'), ('chunk0', 'p0.jsonl'), ('chunk1', 'p1.jsonl')]
SIDES = ('native', 'wasm')
HEAP_BIG = 1000


def load(name):
    p = os.path.join(W, name)
    if not os.path.exists(p):
        raise SystemExit('missing: ' + p)
    return [json.loads(l) for l in open(p)]


def left_of(c, side):
    return c.get(side + '_left')


def mem_blocks(c):
    d = c.get('detail') or {}
    m = (d.get('diffs') or {}).get('mem')
    return m.get('count') if isinstance(m, dict) else None


def main():
    fn_lines = ['run\tva\tname\tverdict\tnative_audited_cases\twasm_audited_cases\t'
                'native_z_n\tnative_z_first\tnative_z_last\tnative_max_n\t'
                'wasm_z_n\twasm_z_first\twasm_z_last\twasm_max_n\tmem_blocks\n']
    per = defaultdict(list)
    audited = defaultdict(int)
    control = None
    for run, fname in RUNS:
        for r in sorted(load(fname), key=lambda r: int(r['va'], 16)):
            label = 'control' if r.get('control') else run
            cs = r.get('cases', [])
            counts = {}
            zcols = []
            zsel = {}
            for side in SIDES:
                au = [left_of(c, side) for c in cs if left_of(c, side) is not None]
                audited[(label, side)] += len(au)
                zs = [left_of(c, side) for c in cs if c.get('pattern') == 'z' and left_of(c, side) is not None]
                z = zs[0] if zs else None
                mx = max((x['n'] for x in au), default=None)
                per[(label, side)].append(z)
                zsel[side] = z
                counts[side] = len(au)
                if z is None:
                    zcols += ['-', '-', '-', '-']
                else:
                    zcols += [str(z['n']), z['first'], z['last'], '-' if mx is None else str(mx)]
            if label == 'control':
                control = (r['va'], r['name'], zsel)
            row = [label, r['va'], r['name'], str(r.get('verdict'))]
            row += [str(counts[s]) for s in SIDES] + zcols
            mems = [mem_blocks(c) for c in cs if mem_blocks(c) is not None]
            row.append(str(mems[0]) if mems else '-')
            fn_lines.append('\t'.join(row) + '\n')
    open(os.path.join(RESULTS, 'ld96_heap_residue.tsv'), 'w').write(''.join(fn_lines))

    sm = ['run\tside\tfunctions\taudited_cases\tz_with_residue\tz_n_min\tz_n_max\tz_n_gt_%d\tz_n_sum\n' % HEAP_BIG]
    for run, _ in RUNS:
        for side in SIDES:
            zs = [z for z in per[(run, side)] if z is not None]
            pos = [z['n'] for z in zs if z['n'] > 0]
            sm.append('\t'.join([
                run, side, str(len(zs)), str(audited[(run, side)]), str(len(pos)),
                str(min(pos)) if pos else '-', str(max(pos)) if pos else '-',
                str(sum(1 for z in zs if z['n'] > HEAP_BIG)), str(sum(pos))]) + '\n')
    if control:
        va, name, z = control
        sm.append('control\t%s\t%s\texpected=1\tnative_n=%s\twasm_n=%s\tnative_first=%s\twasm_first=%s\n' % (
            va, name, z['native']['n'], z['wasm']['n'], z['native']['first'], z['wasm']['first']))
    open(os.path.join(RESULTS, 'ld96_heap_residue_summary.tsv'), 'w').write(''.join(sm))
    print(''.join(sm))
    print('wrote', len(fn_lines) - 1, 'function rows')


if __name__ == '__main__':
    main()
