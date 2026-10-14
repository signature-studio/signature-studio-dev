#!/usr/bin/env python3
"""ld104_reach.py — #2288 (LD-104) c589b0・128f9e0 の spill 宛 24 site の機械語到達性。

IR に site の block が無い理由 (REPORT_2288 §8) を機械語の CFG で確かめる。
  1. 関数入口から jcc / jmp / call の後続を辿り、site に到達できるかを数える (BFS・命令単位)。
  2. c589b0 の定数分岐の枝刈り: c59271 `mov eax,[FLAG]` の読み値 v から、各分岐 (c5927c・c59283・c5928e) の
     成否を算出する (prune_for_v)。v は (3) の支配の測定で c59182 の書込み値 8 に固定される。v ごとの結果も並べる。
  3. 支配・書込み走査 (config の関数区間 boot*.drc.config.json の全命令):
     (a) 入口から c59182 を除くと c59271 に届かない、(b) c5918c〜c59271 に call が無い、
     (c) config 全関数で c5918c〜c59277 の外から内への直接分岐が 0 件 (config 外の image は未走査)。
     FLAG を rip 相対で指す命令の数 (書込み W・読み R・アドレス取得 A)。欠落 store 2 本の rip 参照も数える。
使い方: python3 ld104_reach.py [OUT.tsv]      環境変数: M11_WORK (既定 tools/m11/work)
出力: OUT.tsv (site の到達) と、同じ dir の ld104_checks.txt (枝刈り表・支配・走査)
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
CHECKS = os.path.join(os.path.dirname(os.path.abspath(OUT)), 'ld104_checks.txt')
FLAG = 0x1504dd4
FLAG_WRITE = 0xc59182
FLAG_READ = 0xc59271
FLAG_RANGE = (0xc5918c, 0xc59277)
STORES = (0x1504dd9, 0x1504dda)
SITES = {
    'c589b0': ['c592c2', 'c5a6b4', 'c5a705', 'c5a750', 'c5a811', 'c5bc03', 'c5bc54', 'c5bc9f', 'c5bd1d',
               'c5d121', 'c5d172', 'c5d1bd'],
    '128f9e0': ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012', '1293063', '12930ae',
                '129312c', '129450c', '129455d', '12945a8'],
}
ENTRY = {'c589b0': 0xc589b0, '128f9e0': 0x128f9e0}
# (分岐命令, 比較する値の差分 k, je 系なら True / jne 系なら False)。読み値 v に対し eax は v-6, v-10, v-11 になる
FLAG_BRANCHES = ((0xc5927c, 6, True), (0xc59283, 10, True), (0xc5928e, 11, False))
SPAN = 0x8000
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
DIRECT = re.compile(r'0x[0-9a-f]+$')


def prune_for_v(v):
    prune = set()
    for a, k, zero_taken in FLAG_BRANCHES:
        d = (v - k) & 0xffffffff
        taken = (d == 0) if zero_taken else (d != 0)
        prune.add((a, 'F' if taken else 'T'))
    return prune


def reach(mach, cs, entry, prune, block=frozenset()):
    seen, q, unknown = set(), deque([entry]), 0
    while q:
        a = q.popleft()
        if a in seen or a in block or not (entry <= a < entry + SPAN):
            continue
        seen.add(a)
        ins = next(cs.disasm(mach.read(a - mach.base, 16), a, 1), None)
        if ins is None:
            continue
        mn, op = ins.mnemonic, ins.op_str
        nxt = a + ins.size
        if mn == 'ret' or mn == 'ud2':
            continue
        if mn == 'jmp' and DIRECT.match(op):
            q.append(int(op, 16))
            continue
        if mn == 'jmp':
            unknown += 1
            continue
        if mn.startswith('j') and DIRECT.match(op):
            t = int(op, 16)
            if (a, 'T') not in prune:
                q.append(t)
            if (a, 'F') not in prune:
                q.append(nxt)
            continue
        q.append(nxt)
    return seen, unknown


def config_funcs(base):
    funcs = {}
    for p in glob.glob(os.path.join(W, 'boot*.drc.config.json')):
        for f in json.load(open(p))['functions']:
            try:
                s, e = int(f['startAddr'], 16), int(f['endAddr'], 16)
            except (KeyError, ValueError):
                continue
            if e > s and s >= base and e - s < 0x100000:
                funcs[s] = max(e, funcs.get(s, 0))
    return funcs


def rip_hits(data, base, funcs, targets):
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits = []
    for s, e in sorted(funcs.items()):
        for x in cs.disasm(data[s - base:e - base], s):
            m = RIP.search(x.op_str)
            if not m:
                continue
            d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            t = x.address + x.size + d
            if t not in targets:
                continue
            if x.mnemonic == 'lea':
                kind = 'A'
            elif re.match(r'(?:mov|add|sub|and|or|xor|inc|dec)\w* (?:byte|word|dword|qword) ptr \[rip', x.mnemonic + ' ' + x.op_str):
                kind = 'W'
            else:
                kind = 'R'
            hits.append((x.address, x.mnemonic, x.op_str, kind, s, t))
    return hits


def branches_into(data, base, funcs, lo, hi):
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    into, indirect, direct = [], 0, 0
    for s, e in sorted(funcs.items()):
        for x in cs.disasm(data[s - base:e - base], s):
            if not (x.mnemonic.startswith('j') or x.mnemonic == 'call'):
                continue
            if not DIRECT.match(x.op_str):
                indirect += 1
                continue
            direct += 1
            t = int(x.op_str, 16)
            if lo <= t <= hi and not (lo <= x.address <= hi):
                into.append((x.address, x.mnemonic, x.op_str))
    return into, indirect, direct


def calls_in(mach, cs, lo, hi):
    code = mach.read(lo - mach.base, hi - lo + 16)
    return [(x.address, x.mnemonic, x.op_str) for x in cs.disasm(code, lo) if x.address <= hi and x.mnemonic == 'call']


def main():
    mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    data = open(os.path.join(W, 'm11_image.bin'), 'rb').read()
    rows = ['fn\tsite\treach_none\treach_pruned\tunknown_jmp_none\tverdict_reach']
    checks = []

    def log(s):
        print(s)
        checks.append(s)

    for fn, sites in SITES.items():
        e = ENTRY[fn]
        prune = prune_for_v(8) if fn == 'c589b0' else set()
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
        log('[ld104_reach] %s: site %d / 枝刈り無し到達 %d / 枝刈り後到達 %d / 枝刈り後 DEAD %d (CFG 到達命令 %d -> %d, jmp reg %d -> %d)' % (
            fn, len(sites), sum(1 for s in sites if int(s, 16) in r_none), cnt['reach'], cnt['dead'],
            len(r_none), len(r_pr), u_none, u_pr))

    e = ENTRY['c589b0']
    sites = [int(s, 16) for s in SITES['c589b0']]
    log('[ld104_reach] c589b0 の読み値 v ごとの枝刈り (c59271 の読み値 v に対する分岐の成否・site 到達):')
    scen = [('none', set()), ('NC: c5927c の fall のみ枝刈り', {(0xc5927c, 'F')})]
    scen += [('v=%s' % hex(v), prune_for_v(v)) for v in (6, 8, 10, 11, 0x7fffffff)]
    for name, p in scen:
        r, _ = reach(mach, cs, e, p)
        got = [('%x' % a) for a in sites if a in r]
        pl = ' '.join('%x%s' % (a, m) for a, m in sorted(p))
        log('  %-30s prune=[%s] REACH %2d/12 %s' % (name, pl, len(got), ' '.join(got)))

    r_cut, _ = reach(mach, cs, e, set(), block={FLAG_WRITE})
    r_full, _ = reach(mach, cs, e, set())
    log('[ld104_reach] (a) 支配: c59271 到達 %s -> c59182 を除くと %s / c5918c 到達 %s -> %s' % (
        'Y' if FLAG_READ in r_full else 'N', 'Y' if FLAG_READ in r_cut else 'N',
        'Y' if FLAG_RANGE[0] in r_full else 'N', 'Y' if FLAG_RANGE[0] in r_cut else 'N'))
    cl = calls_in(mach, cs, FLAG_RANGE[0], FLAG_READ)
    log('[ld104_reach] (b) c5918c〜c59271 の call: %d 件 %s' % (len(cl), cl))

    funcs = config_funcs(mach.base)
    into, indirect, direct = branches_into(data, mach.base, funcs, FLAG_RANGE[0], FLAG_RANGE[1])
    log('[ld104_reach] (c) config 関数 %d 本: 直接分岐・call %d 件 / 間接 %d 件。c5918c〜c59277 の外から内への直接分岐 %d 件 %s' % (
        len(funcs), direct, indirect, len(into), into))

    hits = rip_hits(data, mach.base, funcs, {FLAG})
    kinds = {k: sum(1 for h in hits if h[3] == k) for k in 'WRA'}
    log('[ld104_reach] VA 0x%x を rip 相対で指す命令 (config 関数区間): 書込み %d / 読み %d / アドレス取得 lea %d' % (
        FLAG, kinds['W'], kinds['R'], kinds['A']))
    for h in hits:
        log('  %x %s %s (%s) fn %x -> %x' % (h[0], h[1], h[2], h[3], h[4], h[5]))
    st = rip_hits(data, mach.base, funcs, set(STORES))
    log('[ld104_reach] 欠落 store 2 本 (VA 0x%x・0x%x) を rip 相対で指す命令 (config 関数区間): %d 件' % (STORES[0], STORES[1], len(st)))
    for h in st:
        log('  %x %s %s (%s) fn %x -> %x' % (h[0], h[1], h[2], h[3], h[4], h[5]))

    with open(OUT, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    with open(CHECKS, 'w') as fh:
        fh.write('\n'.join(checks) + '\n')
    print('[ld104_reach] -> %s, %s' % (OUT, CHECKS))


if __name__ == '__main__':
    main()
