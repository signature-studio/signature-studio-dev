#!/usr/bin/env python3
"""gen_approx_inc.py — 実機近似表 (snapins/scripts/approx_tables.b64) を fle_approx.inc (C 配列) に変換する。
usage: python3 tools/flelift/rt/gen_approx_inc.py  (出力は rt/fle_approx.inc。手編集禁止)"""
import base64, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', '..', 'targets', 'kilohearts', 'snapins', 'scripts', 'approx_tables.b64')
OUT = os.path.join(HERE, 'fle_approx.inc')
NAMES = ('kh_at_rcp', 'kh_at_rsq_odd', 'kh_at_rsq_even')


def main():
    b64 = ''.join(l for l in open(SRC) if not l.startswith('#'))
    blob = base64.b64decode(''.join(b64.split()))
    assert len(blob) == 3 * 4096 * 4, len(blob)
    vals = struct.unpack('<12288I', blob)
    with open(OUT, 'w') as f:
        f.write('/* 自動生成 (gen_approx_inc.py): 実機 (AMD Ryzen 9 9950X) の rcpps / rsqrtps 近似表。手編集禁止。 */\n')
        for k, nm in enumerate(NAMES):
            t = vals[k * 4096:(k + 1) * 4096]
            f.write('static const uint32_t %s[4096] = {\n' % nm)
            for i in range(0, 4096, 8):
                f.write('  ' + ', '.join('0x%06xu' % v for v in t[i:i + 8]) + ',\n')
            f.write('};\n')
    print('[approx_inc]', OUT, os.path.getsize(OUT), 'B')


if __name__ == '__main__':
    main()
