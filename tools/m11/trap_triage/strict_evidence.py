#!/usr/bin/env python3
"""#1498: strict 候補 (scan_guard.py --report の出力) ごとに判定用の証拠を TSV に書き出す.

各候補 (fn, jcc A, 脱出先 T, ループ先頭 L, 機械語ブロック B) について:
  - 機械語: A の直前 2 命令 (cmp/test の被演算子) と jcc の条件コード
  - IR: B のブロックの終端 (条件分岐か) と、L の頭ブロックの icmp 本数
真偽の判定はこの TSV を入力に件ごとに行う。本スクリプトは判定をしない (SSA 追跡は行わない)。
使い方: python3 strict_evidence.py <IR.ll> --pe <PE.bin> --report <strict.json> --out <out.tsv>
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'guard699'))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
from ldmach import Machine, FnMach  # noqa: E402
import scan_guard as sg  # noqa: E402


def fn_text(text, name):
    m = re.search(r'^define [^@\n]*@%s\(' % re.escape(name), text, re.M)
    if not m:
        return None
    end = text.index('\n}', m.end()) + 2
    return text[m.start():end]


def block_lines(body):
    """ブロック名 -> 本文行 (parse_blocks は行を返さないため別に取る)。"""
    out = {}
    cur = None
    for line in body.split('\n'):
        m = sg.BLK_RE.match(line)
        if m:
            cur = m.group(1) + m.group(2)
            out[cur] = []
        elif cur is not None and line.strip():
            out[cur].append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    cands = json.load(open(a.report))['strict']
    mach = Machine(a.pe)
    rows = []
    cache = {}
    for c in cands:
        name = c['fn']
        if name not in cache:
            body = fn_text(text, name)
            blocks = sg.parse_blocks(body)
            own, _ = sg.owners(blocks)
            va = int(name[len('function_'):], 16)
            cache[name] = (blocks, own, FnMach(mach, va, list(own.keys())), block_lines(body))
        blocks, own, fv, lines = cache[name]
        A = int(c['jcc'], 16)
        ins = fv.ins
        idx = next(i for i, x in enumerate(ins) if x.address == A)
        prev = ['%s %s' % (x.mnemonic, x.op_str) for x in ins[max(0, idx - 2):idx]]
        B = c['block']
        bname = own[int(B, 16)]
        L = int(c['loop_head'], 16)
        lname = own.get(L, '')
        icmp_L = sum(1 for ln in lines.get(lname, []) if ' icmp ' in ln)
        cond_ir_B = 'br i1' in blocks[bname]['term']
        rows.append({
            'fn': name, 'jcc': c['jcc'], 'mnemonic': c['mnemonic'], 'target': c['target'],
            'loop_head': c['loop_head'], 'block': bname,
            'mach_prev2': ' ; '.join(prev), 'ir_block_term': blocks[bname]['term'].strip(),
            'ir_block_cond': int(cond_ir_B), 'ir_loop_head_icmp': icmp_L,
        })
    fields = list(rows[0].keys()) if rows else [
        'fn', 'jcc', 'mnemonic', 'target', 'loop_head', 'block',
        'mach_prev2', 'ir_block_term', 'ir_block_cond', 'ir_loop_head_icmp']
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader()
        w.writerows(rows)
    print('[strict_evidence] rows=%d -> %s' % (len(rows), a.out))


if __name__ == '__main__':
    main()
