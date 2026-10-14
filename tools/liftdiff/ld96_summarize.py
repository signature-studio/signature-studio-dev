#!/usr/bin/env python3
"""LD-96 (#2258): ld96_heap_audit.py の出力 (work/ld96/{solo,p0,p1}.jsonl) を TSV に集計する。

  python3 ld96_summarize.py
    -> results/ld96_heap_residue.tsv         関数ごと (run = solo / chunk0 / chunk1)
    -> results/ld96_heap_residue_summary.tsv run × side (native / wasm) ごとの件数・最小・最大

  n = 高水位より外に残った非 0 バイト数。z = 先頭 case (pattern z)。max = 監査した全 case の最大。
  手順は REPORT_APPENDIX_LD96.md §8.7。
"""
import json, os

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
    fn_lines = ['run\tva\tname\tverdict\taudited_cases\tnative_z_n\tnative_z_first\tnative_z_last\tnative_max_n\t'
                'wasm_z_n\twasm_z_first\twasm_z_last\twasm_max_n\tmem_blocks\n']
    per = {(run, side): [] for run, _ in RUNS for side in SIDES}
    audited = {(run, side): 0 for run, _ in RUNS for side in SIDES}
    control = None
    for run, fname in RUNS:
        recs = sorted(load(fname), key=lambda r: int(r['va'], 16))
        for r in recs:
            cs = r.get('cases', [])
            row = [run, r['va'], r['name'], str(r.get('verdict')), None]
            ncase = None
            for side in SIDES:
                au = [left_of(c, side) for c in cs if left_of(c, side) is not None]
                audited[(run, side)] += len(au)
                zs = [left_of(c, side) for c in cs if c.get('pattern') == 'z' and left_of(c, side) is not None]
                z = zs[0] if zs else None
                mx = max((x['n'] for x in au), default=None)
                per[(run, side)].append(z)
                if z is None:
                    row += ['-', '-', '-', '-']
                else:
                    row += [str(z['n']), z['first'], z['last'], '-' if mx is None else str(mx)]
                ncase = len(au)
            row[4] = str(ncase)
            mems = [mem_blocks(c) for c in cs if mem_blocks(c) is not None]
            row.append(str(mems[0]) if mems else '-')
            fn_lines.append('\t'.join(row) + '\n')
        if run == 'solo' and recs:
            for c in recs[0]['cases']:
                if c.get('pattern') == 'z' and left_of(c, 'native') is not None:
                    control = (recs[0]['va'], recs[0]['name'], c)
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
        va, name, c = control
        sm.append('control\t%s\t%s\texpected=1\tnative_n=%s\twasm_n=%s\tnative_first=%s\twasm_first=%s\n' % (
            va, name, c['native_left']['n'], c['wasm_left']['n'],
            c['native_left']['first'], c['wasm_left']['first']))
    open(os.path.join(RESULTS, 'ld96_heap_residue_summary.tsv'), 'w').write(''.join(sm))
    print(''.join(sm))
    print('wrote', len(fn_lines) - 1, 'function rows')


if __name__ == '__main__':
    main()
