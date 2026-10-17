#!/usr/bin/env python3
"""#4498 (LD-221) 受入 3: 1046a30 の終端 (ret 0x104ccca) より後ろの VA 0x104ccd0〜0x104cfxx 系の定数が、データか関数ポインタかを確定する。

入力: work/m11_image.bin (M11_WORK 環境変数で場所を指定、既定は tools/m11/work)、results/rip_1046a30_3677.tsv
出力: results/const_1046a30_4498.tsv
列: va_hex, rows (IR 件数), mc_insn (機械語の rip 参照の例), mc_width, bytes8 (定数の 8 B 生値), refs (参照の種類), kind
判定:
  - refs: 参照している機械語の命令を列挙する (mulsd/divsd/addsd/movzx/mov の rip 参照 = 値の読み)。
  - kind: 全参照が「値の読み」 (メモリオペランドとして読む命令) なら DATA。call/jmp の間接先になる参照が 1 つでもあれば FUNCPTR。
  - 関数ポインタなら rip 参照は call/jmp になる。本表では 0 件であることを確認する。
"""
import csv
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 0x400000
DATA_OPS = ('mulsd', 'divsd', 'addsd', 'subsd', 'movzx', 'mov', 'movsd', 'movss', 'ucomiss', 'comisd', 'mulss', 'addss')


def main():
    work = os.environ.get('M11_WORK', os.path.join(HERE, '..', 'work'))
    img = open(os.path.join(work, 'm11_image.bin'), 'rb').read()
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, 'results', 'rip_1046a30_3677.tsv')), delimiter='\t')]
    rows = [r for r in rows if r['va_hex'].startswith('0x104c')]
    agg = OrderedDict()
    for r in rows:
        agg.setdefault(r['va_hex'], []).append(r)
    out = ['va_hex\trows\tmc_insn\tmc_width\tbytes8\trefs\tkind']
    fp = 0
    for va_hex in agg:
        va = int(va_hex, 16)
        lva = va - BASE
        raw = img[lva:lva + 8].hex()
        ops = sorted(set(r['mc_insn'].split()[-1] for r in agg[va_hex]))
        kind = 'DATA' if all(o in DATA_OPS for o in ops) else 'FUNCPTR'
        fp += kind == 'FUNCPTR'
        out.append('\t'.join([va_hex, str(len(agg[va_hex])), agg[va_hex][0]['mc_insn'], agg[va_hex][0]['mc_width'],
                              raw, ','.join(ops), kind]))
    open(os.path.join(HERE, 'results', 'const_1046a30_4498.tsv'), 'w').write('\n'.join(out) + '\n')
    print('vas=%d rows=%d funcptr=%d' % (len(agg), len(rows), fp))
    return 1 if fp else 0


if __name__ == '__main__':
    sys.exit(main())
