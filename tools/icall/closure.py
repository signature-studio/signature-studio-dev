#!/usr/bin/env python3
"""closure.py — PE の関数集合 closure (直接 call / 末尾 jmp の推移閉包) を求める.
  python3 closure.py --pe X.dll --roots roots.txt [--max-funcs N] [--stop stop.txt] --out funcs.txt
roots: VA(hex) または "A-B" range (1 行 1 個 / CSV)。出力: "0xA-0xB" 形式 (範囲は .pdata / 次関数境界)。
間接 call の target は静的に不明なので閉包に入らない (監査 audit_icall.py で別途数える)."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_icall as A
from capstone import x86


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--roots', required=True)
    ap.add_argument('--stop')
    ap.add_argument('--max-funcs', type=int, default=100000)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    img = A.Image(a.pe)
    roots = set()
    rng = {}
    for fp in a.roots.split(','):
        for t in open(fp).read().replace(',', '\n').split():
            if '-' in t:
                lo, hi = t.split('-')
                if int(hi, 16) - int(lo, 16) >= 4:      # m6 の ott_ranges.txt には start==end の退化 range がある → 無視して .pdata/境界から求める
                    rng[int(lo, 16)] = int(hi, 16)
                roots.add(int(lo, 16))
            else:
                roots.add(int(t, 16))
    stop = set()
    if a.stop:
        stop = {int(t, 16) for t in open(a.stop).read().replace(',', '\n').split() if t}
    img.set_extra_starts(list(roots))
    dis = A.Disasm(img)
    seen = {}
    work = sorted(roots)
    while work and len(seen) < a.max_funcs:
        f = work.pop()
        if f in seen or f in stop:
            continue
        if not img.is_exec(f):
            continue
        rg = (f, rng[f]) if f in rng else img.func_range(f)
        if not rg:
            continue
        sites = {}
        ins = dis.scan_function(rg[0], rg[1], sites)
        dis.gap_sweep(rg[0], rg[1], ins, sites)
        seen[f] = rg
        for va, i in ins.items():
            if (i.mnemonic == 'call' or i.mnemonic.startswith('j')) and i.operands and i.operands[0].type == x86.X86_OP_IMM:
                t = i.operands[0].imm
                if img.is_exec(t) and not (rg[0] <= t < rg[1]) and t not in seen:
                    if t not in rng:
                        img.set_extra_starts(list(set(seen) | set(roots) | {t}))
                    work.append(t)
    open(a.out, 'w').write(','.join('0x%x-0x%x' % seen[f] for f in sorted(seen)))
    print('closure: %d funcs, %d bytes' % (len(seen), sum(b - a_ for a_, b in seen.values())))


if __name__ == '__main__':
    main()
