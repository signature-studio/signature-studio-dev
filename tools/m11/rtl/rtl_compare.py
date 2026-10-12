#!/usr/bin/env python3
"""RTL 帯の liftdiff 採点 (m11 route=RetDec / flelift route=x64c) を VA 単位で突合し unit 別に集計する (#129)。

usage: rtl_compare.py <rtl_units.json(rtl_range.py --json)> <m11_batch.jsonl> <flelift_batch.jsonl> [--tsv out.tsv] [--md out.md]
batch.jsonl は liftdiff batch の出力 (1 行 1 関数, function.va / verdict)。verdict は liftdiff の
一致(match)/不一致(mismatch)/実行不能(unexec) に正規化して使う。
"""
import collections, json, sys

OV = {  # m11_ov.c の手転記 (RTL 関連)
    0x4120c0: 'InitUnits', 0x41d8f0: '_StartLib', 0x412160: '_InitLib', 0x412510: '再配置表適用',
    0x4133f0: '_UStrAsg', 0x412770: 'Halt 復元', 0x450560: 'SysUtils LCMapString 変換'}


def load(p):
    d = {}
    for l in open(p):
        r = json.loads(l)
        fn = r.get('function') or {}
        va = fn.get('va') if isinstance(fn, dict) else None
        if va is None:
            va = r.get('va') or r.get('fn')
        if va is None:
            continue
        v = r.get('verdict')
        if isinstance(v, dict):
            v = v.get('verdict') or v.get('kind')
        d[int(va, 16) if isinstance(va, str) else va] = (v, r)
    return d


def norm(v):
    return {'match': 'match', 'mismatch': 'mismatch', 'unexec': 'unexec'}.get(v, v)


def main():
    units = json.load(open(sys.argv[1]))['units']
    m, x = load(sys.argv[2]), load(sys.argv[3])
    common = sorted(set(m) & set(x))
    # unit 帯: VMT lo を昇順に並べ、次 unit の VMT lo までをその unit の帯とする近似 (code は unit ごと連続)
    bands = sorted((int(u['vmt_lo'], 16), u['unit']) for u in units if int(u['vmt_lo'], 16) < 0x545000)
    # .text 先頭の System unit は VMT より前から始まる
    bands[0] = (0x401000, bands[0][1])

    def unit_of(va):
        name = None
        for lo, n in bands:
            if va >= lo:
                name = '%s 以降 [%#x〜]' % (n, lo)
        return name

    tab = collections.defaultdict(lambda: collections.Counter())
    for va in common:
        u = unit_of(va)
        tab[u][('m11', norm(m[va][0]))] += 1
        tab[u][('x64c', norm(x[va][0]))] += 1
    tot = collections.Counter()
    for u in tab:
        tot.update(tab[u])
    trans = collections.Counter((norm(m[a][0]), norm(x[a][0])) for a in common)
    lines = ['関数数 %d (両 route 採点あり)' % len(common), '']
    lines.append('| 帯 (VMT 先頭基準の近似。unit 境界ではない) | 関数 | m11 match/mismatch/unexec | x64c match/mismatch/unexec |')
    lines.append('|---|--:|---|---|')
    order = ['%s 以降 [%#x〜]' % (n, lo) for lo, n in bands]
    for u in order:
        c = tab.get(u)
        if not c:
            continue
        n = sum(v for (r, k), v in c.items() if r == 'm11')
        f = lambda r: '/'.join(str(c[(r, k)]) for k in ('match', 'mismatch', 'unexec'))
        lines.append('| %s | %d | %s | %s |' % (u, n, f('m11'), f('x64c')))
    f = lambda r: '/'.join(str(tot[(r, k)]) for k in ('match', 'mismatch', 'unexec'))
    lines.append('| **計** | %d | **%s** | **%s** |' % (len(common), f('m11'), f('x64c')))
    lines += ['', '遷移 (m11 → x64c): ' + ', '.join('%s→%s %d' % (a, b, n) for (a, b), n in sorted(trans.items()))]
    lines += ['', '| m11_ov.c 手転記 | VA | m11 | x64c |', '|---|---|---|---|']
    for a, nm in sorted(OV.items()):
        lines.append('| %s | 0x%x | %s | %s |' % (nm, a, norm(m[a][0]) if a in m else '-', norm(x[a][0]) if a in x else '-'))
    out = '\n'.join(lines)
    print(out)
    if '--md' in sys.argv:
        open(sys.argv[sys.argv.index('--md') + 1], 'w').write(out + '\n')
    if '--tsv' in sys.argv:
        with open(sys.argv[sys.argv.index('--tsv') + 1], 'w') as fo:
            fo.write('#va\tunit\tm11\tx64c\n')
            for va in common:
                fo.write('0x%x\t%s\t%s\t%s\n' % (va, unit_of(va), norm(m[va][0]), norm(x[va][0])))


if __name__ == '__main__':
    main()
