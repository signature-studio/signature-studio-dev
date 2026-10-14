#!/usr/bin/env python3
"""LD-64 (#1854): native 命令単位 trace の rva 集合が、wasm 用 IR (tools/ott/work/ott.ll) の
basic block label (dec_label_pc_<VA>) に一致する割合を数える。

  python3 block_coverage.py <ott.ll> <insn_dir>

insn_dir: results/ld57/insn_<fn>_<pat>.txt (1 行 1 命令・先頭列が rva の 16 進)。
出力: 関数 × pattern ごとに 命令数・distinct rva 数・block label に一致した distinct rva 数。
"""
import glob, os, re, sys

ll, d = sys.argv[1], sys.argv[2]
labels = set()
pat = re.compile(r'^dec_label_pc_([0-9a-f]+):', re.M)
with open(ll, errors='replace') as f:
    labels = {int(m.group(1), 16) for m in pat.finditer(f.read())}

base = 0x180000000
print('fn\tpattern\tinsns\tdistinct_rva\tblock_label_hit\tcoverage')
for p in sorted(glob.glob(os.path.join(d, 'insn_*.txt'))):
    m = re.match(r'insn_(1801[0-9a-f]+)_(\w+)\.txt$', os.path.basename(p))
    if not m:
        continue
    fn, pt = m.group(1), m.group(2)
    rows = [ln.split() for ln in open(p) if ln.strip()]
    rvas = [int(r[0], 16) for r in rows]
    distinct = set(rvas)
    hit = {r for r in distinct if (base + r) in labels}
    print('%s\t%s\t%d\t%d\t%d\t%.1f%%' % (fn, pt, len(rvas), len(distinct), len(hit), 100.0 * len(hit) / max(1, len(distinct))))
