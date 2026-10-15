#!/usr/bin/env python3
"""edge_3972.py (#3972): 指定関数の入口 (alloca 群の直後) と各 ret の直前に m11_eprobe(id, site) を入れる (読み取りだけの計装).
  callchk_3972.py が直接 call の境界しか見ないため、呼出し元 (43c4c0・414bb0・414c70) の内部で
  監視番地の値が変わった区間を、入口・出口の値の比較で絞る。値は変えない (call の追加のみ)。
  usage: edge_3972.py <in.ll> <out.ll> <sites.json>
  id は TARGETS の順 (1 始まり)。site は (fn, kind)。kind = entry または retN。"""
import json, re, sys

src, dst, sites_path = sys.argv[1], sys.argv[2], sys.argv[3]
TARGETS = ['function_43c4c0', 'function_414bb0', 'function_414c70']
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
LABEL = re.compile(r'^[-a-zA-Z$._0-9"]+:')
RET = re.compile(r'^(\s*)ret i64 ')
lines = open(src, errors='replace').read().split('\n')
out, sites = [], {}
cur, n_ret, after_label, entry_done = None, 0, False, False
for ln, line in enumerate(lines, 1):
    m = DEF.match(line)
    if m:
        name = m.group(1)
        cur = TARGETS.index(name) + 1 if name in TARGETS else None
        n_ret, after_label, entry_done = 0, False, False
    if cur is None:
        out.append(line)
        continue
    if not entry_done and LABEL.match(line):
        after_label = True
        out.append(line)
        continue
    if after_label and not entry_done and line.startswith('  ') and ' = alloca ' not in line:
        entry_done = True
        sid = len(sites) + 1
        sites[sid] = {'fn': TARGETS[cur - 1], 'line': ln, 'kind': 'entry'}
        out.append('  call void @m11_eprobe(i32 %d, i32 %d)' % (cur, sid))
        out.append(line)
        continue
    rm = RET.match(line)
    if rm:
        n_ret += 1
        sid = len(sites) + 1
        sites[sid] = {'fn': TARGETS[cur - 1], 'line': ln, 'kind': 'ret%d' % n_ret}
        out.append('%scall void @m11_eprobe(i32 %d, i32 %d)' % (rm.group(1), cur, sid))
    out.append(line)
out.append('declare void @m11_eprobe(i32, i32)')
open(dst, 'w').write('\n'.join(out))
json.dump({str(k): v for k, v in sites.items()}, open(sites_path, 'w'), indent=0)
print('edge sites: %d' % len(sites), file=sys.stderr)
