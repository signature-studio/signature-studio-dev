#!/usr/bin/env python3
"""#3498: strict_evidence.tsv のデータ行 lo..hi (1 始まり, ヘッダ除く) について、判定の機械的な前提を出す.

各行について: (a) jcc を含むブロックの終端 (無条件 br で loop head に入るか)、
(b) 脱出先 (jcc の target) ラベルの preds (脱出先へ入る辺が本体内か後端か)。
判定はしない。真陽性の前提 (入口から脱出先へ直接の経路が無い) の確認に使う。
使い方: python3 judge_entry_check.py <IR.ll> <evidence.tsv> <lo> <hi>
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from strict_evidence import fn_text  # noqa: E402


def target_preds(body, label):
    for ln in body.split('\n'):
        if re.match(r'^%s[:.]' % re.escape(label), ln):
            m = re.search(r'preds = (.*)$', ln)
            return m.group(1) if m else '(preds 注釈なし)'
    return '(ラベル無し)'


def main():
    ir, tsv, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    text = open(ir, errors='replace').read()
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    for i in range(lo, hi + 1):
        r = rows[i - 1]
        body = fn_text(text, r['fn'])
        term = r['ir_block_term'][:60]
        preds = target_preds(body, 'dec_label_pc_' + r['target'])
        print('#%d %s jcc=%s target=%s | jcc ブロック終端: %s | 脱出先 preds: %s' % (
            i, r['fn'], r['jcc'], r['target'], term, preds[:160]))


if __name__ == '__main__':
    main()
