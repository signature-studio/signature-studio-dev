#!/usr/bin/env python3
"""test/cp932_vec.inc を生成する (CP932 DBCS 有効セル全件)。
オラクルは **Python 標準 codec 'cp932'** (shimx の表生成元 = Microsoft bestfit932.txt とは独立実装)。

  python3 scripts/gen_cp932_vec.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'test', 'cp932_vec.inc')

cells = []
for ld in list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD)):
    for tr in range(0x40, 0xFD):
        if tr == 0x7F:
            continue
        try:
            u = bytes([ld, tr]).decode('cp932')
        except UnicodeDecodeError:
            continue
        if len(u) == 1:
            cells.append((ld << 8 | tr, ord(u)))

with open(OUT, 'w') as f:
    f.write('/* 自動生成 (手編集禁止): Python codec cp932 から生成した DBCS 有効セル全件 (code<<16 | unicode)。'
            '再生成: python3 scripts/gen_cp932_vec.py */\n')
    f.write('static const uint32_t k_cp932_cells[] = {\n')
    for i in range(0, len(cells), 8):
        f.write('  ' + ','.join('0x%04X%04X' % (c, u) for c, u in cells[i:i + 8]) + ',\n')
    f.write('};\n')
    f.write('static const unsigned k_cp932_cells_n = %d;\n' % len(cells))
print('gen_cp932_vec: %d cells -> %s' % (len(cells), OUT))
