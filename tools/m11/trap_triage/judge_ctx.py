#!/usr/bin/env python3
"""#3499: strict_evidence.tsv のデータ行 lo..hi (1 始まり, ヘッダ除く) の件ごとに判定用の文脈を出す.

機械語 (jcc 前後・脱出先 T・back-edge)・IR の帰属ブロック B・ループ先頭 L・T・T への preds・関数内の icmp/br i1 数を出す.
判定はしない (同じ値の同一性は人が確かめる)。judge_dump.py の出力を補う。
使い方: LD_M11_PE=<block00031_PE.bin> python3 judge_ctx.py <IR.ll> <evidence.tsv> <lo> <hi> [IR 行数上限=30]
"""
import csv
import os
import re
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ldfix'))
from ldmach import Machine  # noqa: E402


# judge_dump.fn_body は見つからないと '' を返す (件数 0 で黙って進む)。ここでは例外にするため import せず複製している。
def fn_body(text, name):
    m = re.search(r'^define [^@\n]*@%s\(' % re.escape(name), text, re.M)
    end = text.index('\n}', m.end()) + 2
    return text[m.start():end]


def split_blocks(body):
    blocks, cur = {}, None
    for ln in body.split('\n'):
        m = re.match(r'^([A-Za-z0-9_.]+):', ln)
        if m:
            cur = m.group(1)
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(ln)
    return blocks


def show(blocks, bn, n):
    lines = [x for x in blocks.get(bn, []) if x.strip()]
    if bn not in blocks:
        print('   [no block %s]' % bn)
        return
    print('   [%s] (%d lines)' % (bn, len(lines)))
    for x in lines[:n]:
        print('     ' + x)
    if len(lines) > n:
        print('     ... (%d more)' % (len(lines) - n))


def main():
    ir, tsv, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    cap = int(sys.argv[5]) if len(sys.argv) > 5 else 30
    m = Machine(os.environ['LD_M11_PE'])
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    text = open(ir, errors='replace').read()
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    for i in range(lo, hi + 1):
        r = rows[i - 1]
        name = r['fn']
        va = int(name[len('function_'):], 16)
        jcc = int(r['jcc'], 16)
        T = int(r['target'], 16)
        L = int(r['loop_head'], 16)
        print('=' * 100)
        print('#%d %s jcc=%s %s -> T=%s L=%s B=%s' % (i, name, r['jcc'], r['mnemonic'], r['target'], r['loop_head'], r['block']))
        rva, size = m.fns[va]
        ins = list(cs.disasm(m.read(rva, size), va))
        idx = next(k for k, x in enumerate(ins) if x.address == jcc)
        print('-- MACH (jcc 前 14 命令 ～ jcc 後 6 命令)')
        for x in ins[max(0, idx - 14):idx + 7]:
            mark = '  <== jcc' if x.address == jcc else ''
            print('  %x: %s %s%s' % (x.address, x.mnemonic, x.op_str, mark))
        tI = [x for x in ins if x.address >= T][:5]
        print('-- MACH at T: ' + ' ; '.join('%x %s %s' % (x.address, x.mnemonic, x.op_str) for x in tI))
        back = ['%x %s' % (x.address, x.mnemonic) for x in ins
                if x.mnemonic.startswith('j') and x.op_str.strip() == '0x%x' % L]
        print('-- MACH back-edges to L: %s' % back)
        body = fn_body(text, name)
        blocks = split_blocks(body)
        print('-- IR block B:')
        show(blocks, 'dec_label_pc_' + r['block'].replace('dec_label_pc_', ''), cap)
        print('-- IR block L (loop head):')
        show(blocks, 'dec_label_pc_%x' % L, cap)
        print('-- IR preds of T (blocks that br to T):')
        tgt = 'dec_label_pc_%x' % T
        for bn, lines in blocks.items():
            if any(('label %' + tgt) in x for x in lines):
                print('   ' + bn)
        print('-- IR block T:')
        show(blocks, tgt, 8)
        lines = body.split('\n')
        print('-- IR icmp / br i1 in function: %d / %d' % (
            sum(1 for x in lines if ' icmp ' in x), sum(1 for x in lines if 'br i1' in x)))


if __name__ == '__main__':
    main()
