"""L1 復元 pass の前後で、0x1800c2b50 内の到達性 (raw / patched 経路 × L1 の有無) を表示する。

使い方: python3 reach_l1.py <raw.ll> <patched.ll>
  raw.ll     : base 修復後の faithful 経路 IR (N2b を当てない)
  patched.ll : authstub_irpass.py 適用後 IR (N2b-2 を含む)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'liftlib'))

import authstub_irpass as A
from liftlib.passes.l1_restore import restore_l1

FN = 0x1800C2B50
BLOCKS = [0x1800C2D5F, 0x1800C2D6F, 0x1800C2EF4, 0x1800C2F08]


def table(lines):
    ranges = {fva: (s, e) for (fva, s, e) in A.fn_ranges(lines)}
    s, e = ranges[FN]
    blocks, reach = A.reachable_set(lines, s, e)
    row = {}
    for bv in BLOCKS:
        lab = 'dec_label_pc_%x' % bv
        row[bv] = 'absent' if lab not in blocks else ('REACHABLE' if lab in reach else 'unreachable')
    return row


def main():
    raw_path, pat_path = sys.argv[1], sys.argv[2]
    raw = open(raw_path).read().splitlines()
    pat = open(pat_path).read().splitlines()
    rows = [('raw', raw), ('raw + L1', None), ('patched', pat), ('patched + L1', None)]
    print('| 入力 | d5f | d6f | ef4 | f08 |')
    print('|---|---|---|---|---|')
    for name, lines in rows:
        if lines is None:
            base = raw if name == 'raw + L1' else pat
            lines = list(base)
            restore_l1(lines)
        t = table(lines)
        print('| %s | %s | %s | %s | %s |' % (name, t[0x1800C2D5F], t[0x1800C2D6F], t[0x1800C2EF4], t[0x1800C2F08]))


if __name__ == '__main__':
    main()
