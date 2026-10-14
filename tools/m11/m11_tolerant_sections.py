#!/usr/bin/env python3
"""m11_tolerant_sections.py (#2714 §4-2): 寛容起動の skip unit ごとの image 差分 (B) を PE のセクション別に割る.
入力: work/tolerant_units.json (m11_tolerant.mjs の M11_TOLERANT_OUT・skipped[].img_ranges = image offset の [s, e) 区間).
image の offset = LB + RVA (m11_image_gen.py・LB = lb_base.LB). 区間は PE の各セクションの RVA 範囲に割り、どれにも入らない分は (other).
並びは 1 番目 .text B 降順・2 番目 .data+.bss B 降順 (REPORT_N2714 §4-2 の順位)。miss は 1 行にまとめる.
使い方: python3 m11_tolerant_sections.py [PE] [--json work/tolerant_units.json] [--md]   (PE 省略時は M11_PE / FL_WIN64_DIR の既定)"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pefile
from lb_base import LB


def sections(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    return [(s.Name.rstrip(b'\0').decode('latin1'), s.VirtualAddress,
             s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in pe.sections]


def split(ranges, secs):
    out = {}
    for s, e in ranges:
        lo, hi = s - LB, e - LB   # offset → RVA
        covered = 0
        for name, a, b in secs:
            x, y = max(lo, a), min(hi, b)
            if y > x:
                out[name] = out.get(name, 0) + (y - x)
                covered += y - x
        rest = (hi - lo) - covered
        if rest > 0:
            out['(other)'] = out.get('(other)', 0) + rest
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe', nargs='?')
    ap.add_argument('--json', default=os.path.join(HERE, 'work', 'tolerant_units.json'))
    ap.add_argument('--md', action='store_true')
    a = ap.parse_args()
    pe = a.pe or os.environ.get('M11_PE') or (os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin') if os.environ.get('FL_WIN64_DIR') else None)
    if not pe:
        ap.error('PE を指定する (引数・M11_PE・FL_WIN64_DIR のいずれか)')
    secs = sections(pe)
    d = json.load(open(a.json))
    rows, miss, miss_sec = [], {'n': 0, 'B': 0, 'ranges': 0}, {}
    for s in d['skipped']:
        sb = split(s['img_ranges'], secs)
        tot = sum(s['img_ranges'][k][1] - s['img_ranges'][k][0] for k in range(len(s['img_ranges'])))
        if s['kind'] == 'miss':
            miss['n'] += 1
            miss['B'] += tot
            miss['ranges'] += len(s['img_ranges'])
            for k, v in sb.items():
                miss_sec[k] = miss_sec.get(k, 0) + v
            continue
        rows.append(dict(i=s['i'], va=s['va'], kind=s['kind'], text=sb.get('.text', 0), data=sb.get('.data', 0),
                         bss=sb.get('.bss', 0), other={k: v for k, v in sb.items() if k not in ('.text', '.data', '.bss')},
                         total=tot, va_bytes=s['va_bytes'], getmem=s['getmem'], freemem=s['freemem'], n_ranges=len(s['img_ranges'])))
    rows.sort(key=lambda r: (-r['text'], -(r['data'] + r['bss']), r['i']))
    if a.md:
        print('| 順位 | i | VA | 種類 | .text B | .data B | .bss B | 他 B | 区間数 | VA 要求 B | GetMem / FreeMem |')
        print('|---:|---:|---|---|---:|---:|---:|---|---:|---:|---|')
        for k, r in enumerate(rows, 1):
            oth = ', '.join('%s %d' % kv for kv in sorted(r['other'].items())) or '0'
            print('| %d | %d | %s | %s | %d | %d | %d | %s | %d | %s | %d / %d |' % (
                k, r['i'], r['va'], r['kind'], r['text'], r['data'], r['bss'], oth, r['n_ranges'], format(r['va_bytes'], ','), r['getmem'], r['freemem']))
        print('\n- miss %d unit: image 差分 合計 %d B・区間 %d 個 (セクション別: %s)' % (miss['n'], miss['B'], miss['ranges'], ', '.join('%s %d' % kv for kv in sorted(miss_sec.items()))))
    else:
        for k, r in enumerate(rows, 1):
            print(k, r)
        print('miss', miss)
    print('# sections: ' + ', '.join('%s [0x%x,0x%x)' % (n, a_, b_) for n, a_, b_ in secs), file=sys.stderr)


if __name__ == '__main__':
    main()
