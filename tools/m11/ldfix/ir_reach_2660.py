#!/usr/bin/env python3
"""ir_reach_2660.py — #2660 (LD-119) spill 宛 site の IR 到達性検査。

入力: site_dump.py の出力 (OUTDIR/<fn>.txt) の "## IR" 以降の関数本体。
定数畳み込みで死んだと確認した辺 (SRC:DST) を除いた CFG で、TARGET ブロックが entry から到達可能かを返す。
辺を除くほど到達可能性は減る方向なので、除外後も到達可能なら何も言えず、除外後に到達不能なら
「その辺が死んでいれば TARGET は実行されない」ことを示す (除外前に到達可能であることも併せて確認する)。
使い方: python3 ir_reach_2660.py OUTDIR/<fn>.txt TARGET_BLOCK [SRC:DST ...]
"""
import re
import sys


def main():
    dump, target = sys.argv[1], sys.argv[2]
    dead = {tuple(d.split(':', 1)) for d in sys.argv[3:]}
    ir = open(dump).read().split('## IR\n', 1)[1]
    blocks, order, cur = {}, [], None
    for ln in ir.splitlines():
        m = re.match(r'^([A-Za-z0-9_.$-]+):', ln)
        if m:
            cur = m.group(1)
            blocks[cur] = []
            order.append(cur)
        elif cur is not None:
            blocks[cur].append(ln)
    succ = {}
    for b, lines in blocks.items():
        succ[b] = {t for ln in lines for t in re.findall(r'label %([A-Za-z0-9_.$-]+)', ln) if (b, t) not in dead}
    seen, stack = {order[0]}, [order[0]]
    while stack:
        for t in succ.get(stack.pop(), ()):
            if t not in seen:
                seen.add(t)
                stack.append(t)
    print('%s %s (blocks %d, dead edges %d)' % (target, 'reachable' if target in seen else 'UNREACHABLE', len(order), len(dead)))


if __name__ == '__main__':
    main()
