#!/usr/bin/env python3
"""#1091 (LD-33): 負の対照。関数内の全命令 (`; 0x<addr>` 区間) について、隣接段間で IR 区間が変わった件数を数える。

使い方:
  python3 retdec_negctl_1091.py <dump.err> <func_hex> <lo_hex> <hi_hex> [--pairs 15:16,16:17]
  dump.err は retdec_stage_1091.py が --out DIR に残す dump.err (RetDec --print-after-all の出力)。
出力: 段対ごとに、変化した命令アドレスを列挙する。
"""
import re
import sys


def stages(txt, func):
    parts = re.split(r'^\*\*\* IR Dump After (.*?) \*\*\*$', txt, flags=re.M)
    pat = re.compile(rf'define [^\n]*@function_{func}\(.*?\n\}}', re.S)
    out = []
    for i in range(1, len(parts), 2):
        m = pat.search(parts[i + 1])
        if m:
            out.append((i // 2, parts[i], m.group(0)))
    return out


def insn_segs(f):
    marks = [(int(m.group(1), 16), m.start()) for m in re.finditer(r'; 0x([0-9a-f]+)', f)]
    segs = {}
    for k, (a, p) in enumerate(marks):
        e = marks[k + 1][1] if k + 1 < len(marks) else len(f)
        seg = re.sub(r'%\d+', '%N', f[p:e])
        seg = re.sub(r'!\d+', '', seg)
        segs.setdefault(a, seg)
    return segs


def main():
    txt = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    func, lo, hi = sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 16)
    pairs = [(15, 16), (16, 17)]
    if '--pairs' in sys.argv:
        pairs = [tuple(map(int, p.split(':'))) for p in sys.argv[sys.argv.index('--pairs') + 1].split(',')]
    st = {k: insn_segs(f) for k, _, f in stages(txt, func)}
    addrs = sorted(a for a in set().union(*[set(s) for s in st.values()]) if lo <= a <= hi)
    print(f'関数 function_{func}: 命令数 {len(addrs)} (0x{lo:x}-0x{hi:x})')
    for a, b in pairs:
        if a not in st or b not in st:
            print(f'段 {a}→{b}: 段が無い')
            continue
        ch = [x for x in addrs if st[a].get(x) != st[b].get(x)]
        print(f'段 {a}→{b}: 変化 {len(ch)} 命令: ' + ' '.join(f'{x:x}' for x in ch))


if __name__ == '__main__':
    main()
