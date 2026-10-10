#!/usr/bin/env python3
"""trace_entry.py: 全 `define @function_18xxxxxxx` の先頭に ott_trace(va, a0..a3) 呼出を挿入する (差分デバッグ用)。
usage: trace_entry.py in.ll out.ll   (rt/ott_trace.c をリンクすること: OTT_EXTRA_C=ott_trace.c)"""
import re, sys
src = [l for l in open(sys.argv[1]).read().split('\n') if not l.lstrip().startswith('uselistorder')]
out = []
i = 0
n_ins = 0
dre = re.compile(r'^define (\S+) @function_([0-9a-f]+)\((.*)\) (.*)\{$')
while i < len(src):
    l = src[i]
    m = dre.match(l)
    out.append(l)
    i += 1
    if not m:
        continue
    va = int(m.group(2), 16)
    params = [p.strip() for p in m.group(3).split(',') if p.strip()]
    # 先頭ラベル行を出力し, その後 alloca 群の後に挿入 (label 直後 = alloca より前でも可)
    if src[i].endswith(':') and not src[i].startswith(' '):
        out.append(src[i]); i += 1
    ins = []
    args = []
    for k, p in enumerate(params[:4]):
        ty, nm = p.split()[:2]
        t = f'%ott_a{k}_{va:x}'
        if ty == 'i64': args.append(nm)
        elif ty in ('i32', 'i16', 'i8', 'i1'):
            ins.append(f'  {t} = zext {ty} {nm} to i64'); args.append(t)
        elif ty == 'ptr':
            ins.append(f'  {t} = ptrtoint ptr {nm} to i64'); args.append(t)
        elif ty == 'float':
            ins.append(f'  {t}b = bitcast float {nm} to i32'); ins.append(f'  {t} = zext i32 {t}b to i64'); args.append(t)
        elif ty == 'double':
            ins.append(f'  {t} = bitcast double {nm} to i64'); args.append(t)
        elif ty == 'i128':
            ins.append(f'  {t} = trunc i128 {nm} to i64'); args.append(t)
        else:
            args.append('0')
    while len(args) < 4: args.append('0')
    ins.append(f'  call void @ott_trace(i64 {va}, i64 {args[0]}, i64 {args[1]}, i64 {args[2]}, i64 {args[3]})')
    out.extend(ins)
    n_ins += 1
out.append('declare void @ott_trace(i64, i64, i64, i64, i64)')
open(sys.argv[2], 'w').write('\n'.join(out))
print(f'[trace_entry] hooks inserted: {n_ins}')
