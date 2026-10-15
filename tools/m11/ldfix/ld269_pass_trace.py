#!/usr/bin/env python3
"""ld269_pass_trace.py — #5434 (LD-269) RetDec の LLVM pass ごとの dump から、
function_128f9e0 の欠落 label `dec_label_pc_1290645` が消える pass を特定する。

入力: RetDec を --print-after-all で 1 関数だけ実行した stderr (既定 tools/m11/work/pa/stderr.log)。
  生成: retdec-decompiler <PE> -o work/pa/f.drc.c --select-ranges "0x128f9e0-0x1294ab8"
        --select-decode-only --timeout 800 --print-after-all 2> work/pa/stderr.log
出力: results/ld269_pass_trace_128f9e0.tsv (label と switch の有無が変わった dump 番号・pass 名)
使い方: python3 ld269_pass_trace.py [stderr.log]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEF = os.path.join(HERE, '../work/pa/stderr.log')
OUT = os.path.join(HERE, 'results/ld269_pass_trace_128f9e0.tsv')
FN = 'function_128f9e0'
LBL = 'dec_label_pc_1290645:'
SW = 'switch i32 7, label %dec_label_pc_1290698'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEF
    raw = open(src, errors='replace').read()
    blocks = re.split(r'(?m)^\*\*\* IR Dump ', raw)[1:]
    rows = ['dump\tpass\tlabel_1290645\tswitch7']
    n = 0
    prev = None
    for b in blocks:
        if 'define' not in b or FN not in b:
            continue
        head = b.split('\n', 1)[0].replace(' ***', '')
        st = (LBL in b, SW in b)
        if st != prev:
            rows.append('%d\t%s\t%d\t%d' % (n, head, st[0], st[1]))
            prev = st
        n += 1
    rows.append('total\t%d' % n)
    with open(OUT, 'w') as fh:
        fh.write('\n'.join(rows) + '\n')
    print('\n'.join(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
