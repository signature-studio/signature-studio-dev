#!/usr/bin/env python3
"""define 欠落 (ranges の開始 VA に function_<VA> define が無い range) の原因を分類する (#1486)。
  usage: missing_define_classify.py <work dir (ranges.txt / e.drc.ll / e.drc.dsm / e.retdec.log)>
分類 (RetDec 段の出力を根拠にする。pass 鎖では欠落しない: 全 pass の出力で define 数は不変):
  static_linked  = RetDec dsm が `statically linked function` と label した (静的 libc 等の検出で define を出さない)
  symbol_named   = RetDec が function_<VA> でなく関数名 (CreatePlugInstance 等) で define を出す
  other          = 上記以外 (未分類; 0 件であること)
出力: 原因別件数と、各原因の代表 (開始 VA・長さ・参照の有無)。
"""
import collections, os, re, sys

W = sys.argv[1].rstrip('/') + '/'
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(W + 'ranges.txt').read().strip().split(',')]
ll = open(W + 'e.drc.ll').read()
drc = set(int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M))
refs = set(int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\b', ll))
named = set(int(x, 16) for x in re.findall(r'^; function: (?!function_)\S+ at 0x([0-9a-f]+)', open(W + 'e.drc.dsm').read(), re.M))
static = set(int(x, 16) for x in re.findall(r'^; statically linked function: [^\n]*? at 0x([0-9a-f]+)', open(W + 'e.drc.dsm').read(), re.M))
miss = [(a, e) for a, e in rg if a not in drc]
cls = collections.defaultdict(list)
for a, e in miss:
    k = 'static_linked' if a in static else 'symbol_named' if a in named else 'other'
    cls[k].append((a, e))
print('missing_define %d  missing_bytes %d  missing_ref %d' % (
    len(miss), sum(e - a + 1 for a, e in miss), sum(1 for a, _ in miss if a in refs)))
for k in ('static_linked', 'symbol_named', 'other'):
    v = cls[k]
    print('%-13s %4d  ref %3d  bytes %6d' % (k, len(v), sum(1 for a, _ in v if a in refs), sum(e - a + 1 for a, e in v)))
    for a, e in v[:3]:
        print('    rep 0x%x-0x%x len %d ref %s' % (a, e, e - a + 1, 'yes' if a in refs else 'no'))
