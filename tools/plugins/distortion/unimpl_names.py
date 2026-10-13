#!/usr/bin/env python3
"""未実装 `__asm_*` helper の「名前」を許容リストと突合する (judge.py の declares_unimpl は件数のみのため)。
  unimpl_names.py <batch_dir> --blocks B1,B2,... [--allow BLOCK=__asm_name ...]
  <batch_dir>/<block>/p.simd.log の `[simd2] declares ...` 行と `   unimplemented: <sig>` 行を読む。
  許容リストに無い名前が 1 つでもある / simd.log か集計行が無い / 集計行の件数と名前の行数が合わない → exit 1。 全 block 許容内 → exit 0。
"""
import argparse, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('batch_dir')
ap.add_argument('--blocks', required=True)
ap.add_argument('--allow', action='append', default=[], metavar='BLOCK=NAME')
a = ap.parse_args()
allow = {}
for s in a.allow:
    b, n = s.split('=')
    allow.setdefault(int(b), set()).add(n)
bad = 0
for b in (int(x) for x in a.blocks.split(',')):
    p = os.path.join(a.batch_dir, str(b), 'p.simd.log')
    try:
        lines = open(p).read().split('\n')
    except OSError:
        print('FAIL  block %d: %s が読めない' % (b, p))
        bad += 1
        continue
    m = next((re.search(r'unimplemented (\d+)', l) for l in lines if l.startswith('[simd2] declares')), None)
    names = [re.search(r'(__asm_\w+)', l).group(1) for l in lines if l.startswith('   unimplemented:') and '__asm_' in l]
    if not m:
        print('FAIL  block %d: 集計行 `[simd2] declares` が無い' % b)
        bad += 1
        continue
    extra = [n for n in names if n not in allow.get(b, set())]
    ok = int(m.group(1)) == len(names) and not extra
    bad += not ok
    print('%s  block %d: 未実装 %s 件, 名前 %s%s' % ('PASS' if ok else 'FAIL', b, m.group(1), names or '-',
                                              '' if ok else '  <- 許容外 %s / 件数 %s と名前 %d 個' % (extra, m.group(1), len(names))))
print('unimpl_names: %d/%d block 許容内' % (len(a.blocks.split(',')) - bad, len(a.blocks.split(','))))
sys.exit(1 if bad else 0)
