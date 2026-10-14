#!/usr/bin/env python3
"""ld104_reach.py — #2288 (LD-104) c589b0・128f9e0 の spill 宛 24 site の機械語到達性。

IR に site の block が無い理由 (REPORT_2288 §8) を機械語の CFG で確かめる。
  1. 関数入口から jcc / jmp / call の後続を辿り、site に到達できるかを数える (BFS・命令単位)。
  2. 定数分岐の枝刈り: c589b0 の flag 比較連鎖は同じ dword (VA 0x1504dd4) を読む。その唯一の書込み
     (c59182 `mov dword ptr [rip+..], 8`) の値 8 に対し、`sub eax,6` (c59277) の後は 2 で、
     c5927c `je c59299` と c59283 `je c5a7b8` は取られず、c5928e `jne c5d220` は必ず取られる。
     枝刈りは PRUNE_C589B0 に列挙し、枝刈り無し (NONE) の到達性と並べて出す。
  3. 書込み走査: config の関数区間 (boot*.drc.config.json) の全命令で VA 0x1504dd4 を rip 相対で指すものを数える。
使い方: python3 ld104_reach.py [OUT.tsv]      環境変数: M11_WORK (既定 tools/m11/work)
"""
import glob
import json
import os
import re
import sys
from collections import deque

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

W = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'results/ld104_reach.tsv')
FLAG = 0x1504dd4
SITES = {
    'c589b0': ['c592c2', 'c5a6b4', 'c5a705', 'c5a750', 'c5a811', 'c5bc03', 'c5bc54', 'c5bc9f', 'c5bd1d',
               'c5d121', 'c5d172', 'c5d1bd'],
    '128f9e0': ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012', '1293063', '12930ae',
                '129312c', '129450c', '129455d', '12945a8'],
}
ENTRY = {'c589b0': 0xc589b0, '128f9e0': 0x128f9e0}
# (命令, 枝) の組。枝 'T' = 分岐を取る、'F' = 取らない (fallthrough) を削除する
PRUNE_C589B0 = {(0xc5927c, 'T'), (0xc59283, 'T'), (0xc5928e, 'F')}
SPAN = 0x8000


def reach(mach, cs, entry, prune):
    seen, q, unknown = set(), deque([entry]), 0
    while q:
        a = q.popleft()
        if a in seen or not (entry <= a < entry + SPAN):
            continue
        seen.add(a)
        ins = next(cs.disasm(mach.read(a - mach.base, 16), a, 1), None)
        if ins is None:
            continue
        mn, op = ins.mnemonic, ins.op_str
        nxt = a + ins.size
        if mn == 'ret' or mn == 'ud2':
            continue
        if mn == 'jmp' and re.match(r'0x[0-9a-f]+$', op):
            q.append(int(op, 16))
            continue
        if mn == 'jmp':
            unknown += 1
            continue
        if mn.startswith('j') and re.match(r'0x[0-9a-f]+$', op):
            t = int(op, 16)
            if (a, 'T') not in prune:
                q.append(t)
            if (a, 'F') not in prune:
                q.append(nxt)
            continue
        q.append(nxt)
    return seen, unknown


def write_scan(data, base):
    hits = []
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    rip = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
    funcs = {}
    for p in glob.glob(os.path.join(W, 'boot*.drc.config.json')):
        for f in json.load(open(p))['functions']:
            try:
                s, e = int(f['startAddr'], 16), int(f['endAddr'], 16)
            except (KeyError, ValueError):
                continue
            if e > s and s >= base and e - s < 0x100000:
                funcs[s] = max(e, funcs.get(s, 0))
    for s, e in sorted(funcs.items()):
        for x in cs.disasm(data[s - base:e - base], s):
            m = rip.search(x.op_str)
            if not m:
                continue
            d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            if x.address + x.size + d != FLAG:
                continue
            kind = 'W' if re.match(r'(?:mov|add|sub|and|or|xor|inc|dec)\w* (?:byte|word|dword|qword) ptr \[rip', x.mnemonic + ' ' + x.op_str) else 'R'
            hits.append((x.address, x.mnemonic, x.op_str, kind, s))
    return hits


def main():
    mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    data = open(os.path.join(W, 'm11_image.bin'), 'rb').read()
    rows = ['fn\tsite\treach_none\treach_pruned\tunknown_jmp_none\tverdict_reach']
    summary = {}
    for fn, sites in SITES.items():
        e = ENTRY[fn]
        prune = PRUNE_C589B0 if fn == 'c589b0' else set()
        r_none, u_none = reach(mach, cs, e, set())
        r_pr, u_pr = reach(mach, cs, e, prune)
        cnt = {'reach': 0, 'dead': 0}
        for s in sites:
            a = int(s, 16)
            r_no = a in r_none
            r_p = a in r_pr
            v = 'REACH' if r_p else 'DEAD(枝刈り後)'
            cnt['reach' if r_p else 'dead'] += 1
            rows.append('\t'.join([fn, s, 'Y' if r_no else 'N', 'Y' if r_p else 'N', str(u_none), v]))
        summary[fn] = (len(sites), cnt, len(r_none), len(r_pr), u_none, u_pr)
        print('[ld104_reach] %s: site %d / 枝刈り無し到達 %d / 枝刈り後到達 %d / 枝刈り後 DEAD %d (CFG 到達命令 %d -> %d, jmp reg %d -> %d)' % (
            fn, len(sites), sum(1 for s in sites if int(s, 16) in r_none), cnt['reach'], cnt['dead'],
            len(r_none), len(r_pr), u_none, u_pr))
    hits = write_scan(data, mach.base)
    W_hits = [h for h in hits if h[3] == 'W']
    R_hits = [h for h in hits if h[3] == 'R']
    print('[ld104_reach] VA 0x%x を rip 相対で指す命令 (config 関数区間): 書込み %d / 読み %d' % (FLAG, len(W_hits), len(R_hits)))
    for h in hits:
        print('  %x %s %s (%s) fn %x' % (h[0], h[1], h[2], h[3], h[4]))
    with open(OUT, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('[ld104_reach] -> %s' % OUT)


if __name__ == '__main__':
    main()
