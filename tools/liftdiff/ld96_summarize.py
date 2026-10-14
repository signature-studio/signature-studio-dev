#!/usr/bin/env python3
"""LD-96 (#2258): ld96_heap_audit.py の出力 (work/ld96/*.jsonl) を results/ld96_heap_residue_19.tsv に集計する。

  python3 ld96_summarize.py   (先に work/ld96/{solo_final,p0_final,p1_audit}.jsonl を作る。手順は REPORT_APPENDIX_LD96.md §8)
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work', 'ld96')
OUT = os.path.join(HERE, 'results', 'ld96_heap_residue_19.tsv')


def load(name):
    p = os.path.join(W, name)
    return {json.loads(l)['va']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}


def left(c, side):
    x = c.get(side)
    return x['n'] if x else 0


def main():
    solo = load('solo_final.jsonl')
    full = {}
    full.update(load('p0_final.jsonl'))
    full.update(load('p1_audit.jsonl'))
    lines = ['va\tname\tverdict_solo\tverdict_full\tfull_part\tfull_cases\twasm_left_max_n\twasm_left_first_case_n\twasm_left_first_case_at\tnative_left_max_n\tfull_pdiff_mem\n']
    for va in sorted(solo):
        f = full.get(va, {})
        cs = f.get('cases', [])
        wmax = max((left(c, 'wasm_left') for c in cs), default=0)
        nmax = max((left(c, 'native_left') for c in cs), default=0)
        first = (cs[0].get('wasm_left') or {'n': 0, 'first': '-'}) if cs else {'n': 0, 'first': '-'}
        mem = None
        for c in cs:
            d = c.get('detail') or {}
            m = (d.get('diffs') or {}).get('mem')
            if m:
                mem = m.get('count')
                break
        lines.append('%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s\t%d\t%s\n' % (
            va, solo[va]['name'], solo[va]['verdict'], f.get('verdict', '-'), f.get('part', '-'), len(cs), wmax,
            first['n'], first['first'] if first['n'] else '-', nmax, mem if mem is not None else '-'))
    open(OUT, 'w').write(''.join(lines))
    print('wrote', OUT, len(lines) - 1, 'rows')


if __name__ == '__main__':
    main()
