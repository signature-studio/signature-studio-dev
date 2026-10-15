#!/usr/bin/env python3
"""ld269_reach.py — #5434 (LD-269) function_128f9e0 の機械語 CFG で、入口から各 site へ到達できるかを調べる。

入力: tools/m11/work/boot3.drc.dsm (RetDec の機械語表・直接の分岐のみ扱う)。
辺: jcc / jmp は分岐先と fall-through (jmp は fall-through なし)、call は fall-through のみ、ret は終端。
間接分岐 (`jmp reg`/`jmp qword ptr`) は本関数に無いことを確認してから使う (無ければ中止する)。
出力: results/ld269_reach_128f9e0.tsv (site ごとの到達可否・存在する場合の経路上の最初の辺)
使い方: python3 ld269_reach.py
"""
import os
import re
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
DSM = os.path.join(HERE, '../work/boot3.drc.dsm')
OUT = os.path.join(HERE, 'results/ld269_reach_128f9e0.tsv')
FN, FN_END = 0x128f9e0, 0x1294ab8
ENTRY = FN
SITES = ['12906d1', '1291ac3', '1291b14', '1291b5f', '1291c20', '1293012',
         '1293063', '12930ae', '129312c', '129450c', '129455d', '12945a8']
STORE_OF_DISPATCH = 0x1290591  # mov dword ptr [rip+...], 7 (ディスパッチ値の store)
GAP_LO, GAP_HI = 0x1290645, 0x129460b


def load():
    ins = {}
    for l in open(DSM, errors='replace'):
        m = re.match(r'0x([0-9a-f]+):\s+(?:[0-9a-f]{2} ?)+\s+(.*)', l.rstrip('\n'))
        if not m:
            continue
        a = int(m.group(1), 16)
        if FN <= a < FN_END:
            ins[a] = m.group(2)
    return ins


def succ_map(ins):
    addrs = sorted(ins)
    nxt_of = {a: (addrs[i + 1] if i + 1 < len(addrs) else None) for i, a in enumerate(addrs)}
    out = {}
    for a in addrs:
        t = ins[a]
        nxt = nxt_of[a]
        m = re.match(r'(j\w+)\s+0x([0-9a-f]+)', t)
        if m and m.group(1) == 'jmp':
            out[a] = [int(m.group(2), 16)]
        elif m:
            out[a] = [int(m.group(2), 16)] + ([nxt] if nxt is not None else [])
        elif t.startswith('ret'):
            out[a] = []
        else:
            out[a] = [nxt] if nxt is not None else []
    return out


def main():
    ins = load()
    indirect = [(a, t) for a, t in ins.items() if re.match(r'jmp\s+(?!0x)', t)]
    if indirect:
        print('[ld269] 間接分岐あり (%d 件)。BFS の前提を満たさないので中止' % len(indirect))
        return 1
    sm = succ_map(ins)
    # 定数 7 の dispatch (0x1290680〜0x129069d): eax=7 → sub6=1, sub4=-3, sub1=-4 で、0x129069d の jne は必ず 129460b へ
    # (0x129068b の je・0x1290692 の je は not taken)。値 7 の経路だけを残す。
    sm[0x129068b] = [0x129068d]
    sm[0x1290692] = [0x1290698]
    sm[0x129069d] = [0x129460b]
    seen = {ENTRY: None}
    q = deque([ENTRY])
    while q:
        a = q.popleft()
        for b in sm.get(a, []):
            if b in ins and b not in seen:
                seen[b] = a
                q.append(b)
    rows = ['site\treachable\tin_gap_1290645_129460b\tnote']
    for s in SITES:
        a = int(s, 16)
        rows.append('%s\t%d\t%d\t' % (s, a in seen, GAP_LO <= a < GAP_HI))
    rows.append('dispatch_store\t%d\t-\t%s' % (STORE_OF_DISPATCH in seen, 'mov dword [rip+..],7'))
    rows.append('dispatch_load_0x1290680\t%d\t-\t%s' % (0x1290680 in seen, 'eax=global (固定値 7 の前提)'))
    # 支配の確認: store (0x1290591) を除くと、入口から dispatch load に届くか
    nostore = {ENTRY: None}
    q2 = deque([ENTRY])
    while q2:
        a = q2.popleft()
        for b in sm.get(a, []):
            if b in ins and b != STORE_OF_DISPATCH and b not in nostore:
                nostore[b] = a
                q2.append(b)
    rows.append('dispatch_load_without_store\t%d\t-\tstore を除いても届けば 7 の前提は崩れる' % (0x1290680 in nostore))
    gap_ins = [a for a in ins if GAP_LO <= a < GAP_HI]
    rows.append('gap_insns_reached\t%d\tof\t%d\t%x..%x' % (sum(a in seen for a in gap_ins), len(gap_ins), GAP_LO, GAP_HI))
    rows.append('reached_insns\t%d\tof\t%d' % (len(seen), len(ins)))
    with open(OUT, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('\n'.join(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
