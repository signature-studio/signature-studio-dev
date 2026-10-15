#!/usr/bin/env python3
# (診断) 未修復 comis の周辺 4 行を一覧表示する
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ir6_pass as p6

src = sys.argv[1]
lines = open(src).read().split('\n')
sites = [i for i, l in enumerate(lines) if 'void @__asm_' in l and 'comis' in l]
nfix = 0
for idx in sites:
    pc = p6.parse_call(lines[idx])
    if pc is None:
        continue
    # find branch
    bw = None
    for j in range(idx+1, min(idx+26, len(lines))):
        l = lines[j]
        if re.match(r"^  br i1 ", l):
            bw = (j, l)
            break
        if re.match(r"^  call void @__asm_", l):
            break
    print('idx=%d  %s' % (idx, lines[idx].strip()[:80]))
    print('    br at %s : %s' % (None if not bw else bw[0], None if not bw else bw[1].strip()[:80]))
    if bw is None:
        nfix += 1
print('no-br sites:', nfix, '/', len(sites))
