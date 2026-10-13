#!/usr/bin/env python3
"""m11_remap_count.py — IR 中の未 remap な image VA 即値の件数 (#403 受入 3).
  usage: m11_remap_count.py IR.ll [--assert-clean]
  IR 中の `inttoptr i64 <10進> to ptr` のうち、値が image VA 範囲 [IMG, IMG+SIZE) に残るものを数える
  (= VA→LVA remap 漏れの候補)。命令形 (`%x = inttoptr ...`) と式形を分けて集計する。
  --assert-clean: 残件数が 0 でなければ exit 1 (ネガティブコントロールは tools/m11/m11_remap_count_negctl.sh)。
  既定は測定のみ (exit 0)。値は tools/m11/REPORT_N403.md §3 に転記する。
"""
import re
import sys

IMG = 0x400000       # PE preferred ImageBase (lb_base.py IMG_BASE)
SIZE = 0x1ac0000     # image 範囲 (lb_check.py の 0x1ac0000 と同値)
PAT = re.compile(r'inttoptr i64 (-?\d+) to ptr')


def count(path):
    s = open(path).read()
    instr = expr = instr_bad = expr_bad = 0
    for line in s.split('\n'):
        for m in PAT.finditer(line):
            v = int(m.group(1))
            bad = IMG <= v < IMG + SIZE
            if re.match(r'\s*%', line):
                instr += 1
                instr_bad += bad
            else:
                expr += 1
                expr_bad += bad
    return dict(instr_total=instr, instr_unremapped=instr_bad,
                expr_total=expr, expr_unremapped=expr_bad,
                unremapped=instr_bad + expr_bad)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    res = count(args[0])
    res['ir'] = args[0]
    print(res)
    if '--assert-clean' in sys.argv and res['unremapped'] != 0:
        print('FAIL: unremapped image-VA inttoptr = %d' % res['unremapped'])
        sys.exit(1)
