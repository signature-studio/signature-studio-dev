#!/usr/bin/env python3
"""BLK スロットへの store を IR 上で数える (#3150)。

既定: BLK+0x8 (9048072) と BLK+0x10 (9048080) と、エラーコード格納先 (7155720) への
定数 store を関数ごとに数える。`--fn NAME` を付けると、その関数の BLK store を
値の定義行つきで列挙する。

使い方 (stage-1 後の fw_flat4_canon3.ll に対して):
  python3 fw_blk_writers.py tools/plugins/work/fw/fw_flat4_canon3.ll
  python3 fw_blk_writers.py tools/plugins/work/fw/fw_flat4_canon3.ll --fn function_405670
"""
import argparse
import collections
import re

BLK8, BLK10, ERRCODE = 9048072, 9048080, 7155720

fn_re = re.compile(r'^define .*?@([\w.]+)\(')
ptr_re = re.compile(r'^\s*(%[\w.]+) = inttoptr i64 (\d+) to ptr')
def_re = re.compile(r'^\s*(%[\w.]+) = (.*)')
st_re = re.compile(r'^\s*store (i\d+) (\S+), ptr (%[\w.]+)')


def scan(path, want_fn=None):
    """関数ごとに (行, 関数, 型, 値, 番地) を返す。want_fn があればその関数の定義も集める。"""
    hits, defs, fn, ptrs = [], {}, None, {}
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            if line.startswith('define '):
                m = fn_re.match(line)
                fn, ptrs, defs = (m.group(1) if m else '?'), {}, {}
                continue
            if fn is None:
                continue
            m = ptr_re.match(line)
            if m:
                ptrs[m.group(1)] = int(m.group(2))
                continue
            if want_fn is not None and fn == want_fn:
                d = def_re.match(line)
                if d:
                    defs[d.group(1)] = (ln, d.group(2).strip()[:150])
            m = st_re.match(line)
            if m and m.group(3) in ptrs and ptrs[m.group(3)] in (BLK8, BLK10, ERRCODE):
                hits.append((ln, fn, m.group(1), m.group(2), ptrs[m.group(3)], defs.get(m.group(2))))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ll')
    ap.add_argument('--fn')
    a = ap.parse_args()
    hits = scan(a.ll, a.fn)
    if a.fn:
        for ln, fn, ty, val, addr, d in hits:
            if fn == a.fn:
                print(f'{ln} store {ty} {val} -> {addr} | def: {d[0] if d else "-"} {d[1] if d else ""}')
        return
    per = collections.Counter((addr, val) for _, _, _, val, addr, _ in hits if val in ('1', '203'))
    print('BLK/ERRCODE stores total:', len(hits))
    for (addr, val), n in sorted(per.items()):
        print(f'literal {val} -> {addr}: {n} stores')
    by_fn = collections.Counter((fn, addr) for _, fn, _, val, addr, _ in hits if val == '1')
    print('functions storing literal 1 (fn, addr): distinct =', len(by_fn))
    for (fn, addr), n in sorted(by_fn.items(), key=lambda x: x[0][0])[:80]:
        print(f'  {fn} -> {addr} x{n}')


if __name__ == '__main__':
    main()
