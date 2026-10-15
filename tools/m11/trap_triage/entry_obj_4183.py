#!/usr/bin/env python3
"""entry_obj_4183.py (#4183): 指定関数の入口で第 1 引数 (obj 候補) の値を stderr に出す計装 IR を作る.

  usage: entry_obj_4183.py --src <boot_sw.ll> --out <dir> --fns f1,f2,...
  出力: <out>/boot_ob.ll (計装 IR), <out>/ob_sites.json (site id -> 関数名)。
  計装は各関数の先頭 (alloca とラベルの後) に m11_entry(i64 第1引数, i32 site) の呼出しを 1 件足すだけ。
  行: `[ob] site=<id> val=<第1引数の 64bit 値> hit=<通算>`。
"""
import json, os, re, sys

args = sys.argv[1:]
def opt(name, dflt):
    return args[args.index(name) + 1] if name in args else dflt
src = opt('--src', '')
out = opt('--out', '')
fns = set(opt('--fns', '').split(',')) - {''}
os.makedirs(out, exist_ok=True)

DEF = re.compile(r'^define [^@]*@([-a-zA-Z$._0-9"]+)\((i64|i32|ptr) (%[-a-zA-Z$._0-9]+)')
ALLOCA = re.compile(r'^\s*%\S+ = alloca ')
LABEL = re.compile(r'^[-a-zA-Z$._0-9"]+:\s*$')
lines = open(src).read().split('\n')
res, sites = [], {}
sid = 900000
i = 0
while i < len(lines):
    ln = lines[i]
    res.append(ln)
    m = DEF.match(ln)
    if not (m and m.group(1) in fns):
        i += 1
        continue
    name, ty, arg = m.group(1), m.group(2), m.group(3)
    j = i + 1
    while j < len(lines) and (ALLOCA.match(lines[j]) or LABEL.match(lines[j])):
        res.append(lines[j]); j += 1
    sid += 1
    sites[str(sid)] = name
    if ty == 'i64':
        v = arg
    elif ty == 'i32':
        res.append('  %%ob_x_%d = zext i32 %s to i64' % (sid, arg)); v = '%%ob_x_%d' % sid
    else:
        res.append('  %%ob_x_%d = ptrtoint ptr %s to i64' % (sid, arg)); v = '%%ob_x_%d' % sid
    res.append('  call void @m11_entry(i64 %s, i32 %d)' % (v, sid))
    i = j

text = '\n'.join(res)
if 'declare void @m11_entry(' not in text:
    text = text.replace('\ndefine ', '\ndeclare void @m11_entry(i64, i32)\n\ndefine ', 1)
open(os.path.join(out, 'boot_ob.ll'), 'w').write(text)
json.dump(sites, open(os.path.join(out, 'ob_sites.json'), 'w'), indent=1)
print('entry sites: %d (%s)' % (len(sites), ','.join(sorted(set(sites.values())))))
