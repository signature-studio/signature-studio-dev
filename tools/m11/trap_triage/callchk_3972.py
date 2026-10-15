#!/usr/bin/env python3
"""callchk_3972.py (#3972): IR の各 call 命令の直後に m11_callchk(site) を入れる (読み取りだけの計装).
  store / copy / rep 系の計装が捕まえなかった書込み (C 側 helper 内の書込み等) を、
  「どの call の直後に監視番地の値が変わったか」で拾うための派生。
  usage: callchk_3972.py <in.ll> <out.ll> <sites.json>
  call の追加のみ (IR の値・分岐は不変)。llvm.* intrinsic と m11_* 自身は除外する。"""
import json, re, sys

src, dst, sites_path = sys.argv[1], sys.argv[2], sys.argv[3]
CALL = re.compile(r'^(\s*)(%[-a-zA-Z$._0-9]+ = )?call (?!.*@llvm\.)(?!.*@m11_).*?@([-a-zA-Z$._0-9"]+)\(')
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
lines = open(src, errors='replace').read().split('\n')
out, sites, fn = [], {}, '?'
for ln, line in enumerate(lines, 1):
    m = DEF.match(line)
    if m:
        fn = m.group(1)
    out.append(line)
    cm = CALL.match(line)
    if not cm:
        continue
    sid = len(sites) + 1
    sites[sid] = {'fn': fn, 'line': ln, 'call': cm.group(3)}
    out.append('%scall void @m11_callchk(i32 %d)' % (cm.group(1), sid))
out.append('declare void @m11_callchk(i32)')
open(dst, 'w').write('\n'.join(out))
json.dump({str(k): v for k, v in sites.items()}, open(sites_path, 'w'), indent=0)
print('callchk sites: %d' % len(sites), file=sys.stderr)
