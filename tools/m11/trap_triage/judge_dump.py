#!/usr/bin/env python3
"""#1653: strict_evidence.tsv のデータ行 lo..hi (1 始まり, ヘッダ除く) を件ごとに判定用にダンプする.

各行について: 機械語の cmp 被演算子・jcc、ループ先頭 (loop_head) の icmp、帰属ブロックの終端と icmp を出す.
判定はしない (SSA 追跡は人が行う)。
使い方: python3 judge_dump.py <IR.ll> <evidence.tsv> <lo> <hi>
"""
import csv
import re
import sys


def fn_body(text, name):
    m = re.search(r'^define [^@\n]*@%s\(' % re.escape(name), text, re.M)
    if not m:
        return ''
    end = text.index('\n}', m.end()) + 2
    return text[m.start():end]


def block(body, bname):
    out = []
    on = False
    for ln in body.split('\n'):
        if re.match(r'^[A-Za-z0-9_.]+:', ln):
            on = ln.split(':')[0] == bname
        if on:
            out.append(ln)
    return out


def main():
    ir, tsv, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    text = open(ir, errors='replace').read()
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    for i in range(lo, hi + 1):
        r = rows[i - 1]
        body = fn_body(text, r['fn'])
        lh = block(body, 'dec_label_pc_' + r['loop_head'])
        bl = block(body, r['block'])
        print('#%d %s jcc=%s %s tgt=%s lh=%s blk=%s' % (
            i, r['fn'], r['jcc'], r['mnemonic'], r['target'], r['loop_head'], r['block']))
        print('  MACH: ' + r['mach_prev2'])
        print('  LH-icmp: ' + ' | '.join(x.strip() for x in lh if ' icmp ' in x)[:300])
        print('  BLK-term: ' + r['ir_block_term'][:150])
        print('  BLK-icmp: ' + ' | '.join(x.strip() for x in bl if ' icmp ' in x)[:300])


if __name__ == '__main__':
    main()
