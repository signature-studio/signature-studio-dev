#!/usr/bin/env python3
"""#3492: strict 証拠表の行 lo..hi (1 始まり, ヘッダ除く) について件ごとの判定材料を出す (判定はしない).

各行: 機械語の jcc 直前の命令 (比較の被演算子) / 帰属ブロック B の IR / ループ先頭 L の IR /
L へ入るブロック / 脱出先 T へ IR で分岐するブロックと終端 / 比較レジスタの reg2mem 参照行.
真偽は人が SSA を遡って決める (レジスタ名の一致だけでは根拠にしない)。
使い方: python3 judge_ctx.py <IR.ll> --pe <PE.bin> --tsv <evidence.tsv> --lo 241 --hi 288
"""
import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'guard699'))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
from ldmach import Machine, FnMach  # noqa: E402
import scan_guard as sg  # noqa: E402

REG_RE = re.compile(r'\b(e[abcd]x|e[sd]i|e[sb]p|r(?:[89]|1[0-5]))d?\b')


def to64(tok):
    m = re.fullmatch(r'e([abcd]x|[sd]i|[sb]p)', tok)
    if m:
        return 'r' + m.group(1)
    m = re.fullmatch(r'(r(?:[89]|1[0-5]))d?', tok)
    if m:
        return m.group(1)
    return None


def fn_body(text, name):
    m = re.search(r'^define [^@\n]*@%s\(' % re.escape(name), text, re.M)
    end = text.index('\n}', m.end()) + 2
    return text[m.start():end]


def block_lines(body):
    out = {}
    cur = None
    for line in body.split('\n'):
        m = sg.BLK_RE.match(line)
        if m:
            cur = m.group(1) + m.group(2)
            out[cur] = []
        elif cur is not None and line.strip():
            out[cur].append(line.rstrip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--tsv', required=True)
    ap.add_argument('--lo', type=int, required=True)
    ap.add_argument('--hi', type=int, required=True)
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    rows = list(csv.DictReader(open(a.tsv), delimiter='\t'))
    mach = Machine(a.pe)
    cache = {}
    for i in range(a.lo, a.hi + 1):
        r = rows[i - 1]
        name = r['fn']
        if name not in cache:
            body = fn_body(text, name)
            blocks = sg.parse_blocks(body)
            own, _ = sg.owners(blocks)
            va = int(name[len('function_'):], 16)
            cache[name] = (body, blocks, own, FnMach(mach, va, list(own.keys())), block_lines(body))
        body, blocks, own, fv, lines = cache[name]
        A = int(r['jcc'], 16)
        ins = fv.ins
        idx = next(k for k, x in enumerate(ins) if x.address == A)
        cmp_i = [x for x in ins[max(0, idx - 2):idx] if x.mnemonic in ('cmp', 'test')]
        cmp_op = cmp_i[-1].op_str if cmp_i else ''
        regs = sorted(set(to64(t) for t in REG_RE.findall(cmp_op) if to64(t)))
        T = int(r['target'], 16)
        L = int(r['loop_head'], 16)
        B = own[int(r['block'], 16)]
        Lname = own.get(L, '')
        print('=' * 78)
        print('#%d %s jcc=%s %s -> T=%s L=%s B=%s' % (i, name, r['jcc'], r['mnemonic'], r['target'], r['loop_head'], B))
        print('MACH (jcc 直前 10 命令 + jcc):')
        for x in ins[max(0, idx - 10):idx + 1]:
            print('  %x %s %s' % (x.address, x.mnemonic, x.op_str))
        print('CMP 被演算子: %s | 64bit reg: %s' % (cmp_op, ','.join(regs) or '(なし)'))
        print('IR B %s:' % B)
        for ln in lines.get(B, [])[:40]:
            print('  ' + ln)
        print('IR L %s (L へ分岐するブロック: %s):' % (Lname, ','.join(
            n for n, b in blocks.items() if L in b['succ'])))
        for ln in lines.get(Lname, [])[:40]:
            print('  ' + ln)
        exits = [n for n, b in blocks.items() if T in b['succ']]
        print('IR で T=%x へ分岐するブロック (%d): %s' % (T, len(exits), ','.join(exits[:12])))
        for n in exits[:6]:
            print('  [%s] %s' % (n, blocks[n]['term'].strip()[:200]))
        for rg in regs:
            hits = [ln for ln in body.split('\n') if re.search(r'%%%s\.[0-9]' % rg, ln)]
            print('REG %s reg2mem/reload 行 (%d 件, 先頭 12):' % (rg, len(hits)))
            for ln in hits[:12]:
                print('  ' + ln.strip()[:160])


if __name__ == '__main__':
    main()
