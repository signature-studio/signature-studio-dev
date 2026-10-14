#!/usr/bin/env python3
"""watch_fn_2254.py (#2254): watch_store_682.py の関数範囲限定版。指定した関数の中の store だけに m11_sw を入れる.
  usage: watch_fn_2254.py <fn1,fn2,...> [--src work/boot_final3.ll] [--out work/probe2254]
  生成: <out>/boot_sw.ll と <out>/sites.json (site id -> {fn, line, store})。
  計装は call の追加のみ (IR の値・分岐は不変)。全 store 計装 (watch_store_682.py) が unit 106 で止まるため、対象を絞って計装量を減らす。"""
import json, os, re, sys

args = sys.argv[1:]
FNS = set(args[0].split(',')) if args and not args[0].startswith('--') else set()
def opt(name, dflt):
    return args[args.index(name) + 1] if name in args else dflt
HERE = os.path.dirname(os.path.abspath(__file__)); M11 = os.path.join(HERE, '..')
src_path = opt('--src', os.path.join(M11, 'work', 'boot_final3.ll'))
out = opt('--out', os.path.join(M11, 'work', 'probe2254'))
os.makedirs(out, exist_ok=True)

STORE = re.compile(r'^(\s*)store (.*), ptr (nonnull )?(%[-a-zA-Z$._0-9]+|@[-a-zA-Z$._0-9"]+|inttoptr \(i64 (-?\d+) to ptr\)|null)(, align \d+)?\s*$')
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
WIDTH = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'ptr': 4, 'float': 4, 'double': 8}

def value_i32(vs, sid, ind, out_lines):
    ty, _, op = vs.partition(' ')
    if ty not in ('i8', 'i16', 'i32', 'i64', 'ptr') or not op:
        return '0'
    if op.startswith('%'):
        if ty == 'i32':
            return op
        if ty == 'ptr':
            out_lines.append('%s%%wsv_%d = ptrtoint ptr %s to i32' % (ind, sid, op))
        elif ty == 'i64':
            out_lines.append('%s%%wsv_%d = trunc i64 %s to i32' % (ind, sid, op))
        else:
            out_lines.append('%s%%wsv_%d = zext %s %s to i32' % (ind, sid, ty, op))
        return '%%wsv_%d' % sid
    if re.match(r'^-?\d+$', op):
        return str(int(op) & 0xffffffff)
    if op == 'null':
        return '0'
    if op.startswith('@') and ty == 'ptr':
        return 'ptrtoint (ptr %s to i32)' % op
    return '0'

lines = open(src_path).read().split('\n')
out_lines = []
sites = {}
fn = '?'
inst = 0
for ln, line in enumerate(lines, 1):
    m = DEF.match(line)
    if m:
        fn = m.group(1)
    out_lines.append(line)
    if not line.startswith(' ') or not line.lstrip().startswith('store '):
        continue
    if fn not in FNS:
        continue
    sm = STORE.match(line)
    if not sm:
        continue
    ind, addr = sm.group(1), sm.group(4)
    sid = len(sites) + 1
    sites[sid] = {'fn': fn, 'line': ln, 'store': line.strip()}
    if addr.startswith('%'):
        out_lines.append('%s%%wsa_%d = ptrtoint ptr %s to i32' % (ind, sid, addr))
        a = '%%wsa_%d' % sid
    elif addr.startswith('@'):
        a = 'ptrtoint (ptr %s to i32)' % addr
    elif addr == 'null':
        a = '0'
    else:
        a = str(int(sm.group(5)) & 0xffffffff)
    v = value_i32(sm.group(2), sid, ind, out_lines)
    w = WIDTH.get(sm.group(2).partition(' ')[0], 16)
    out_lines.append('%scall void @m11_sw(i32 %s, i32 %s, i32 %d, i32 %d)' % (ind, a, v, sid, w))
    inst += 1
out_lines.append('declare void @m11_sw(i32, i32, i32, i32)')
open(os.path.join(out, 'boot_sw.ll'), 'w').write('\n'.join(out_lines))
json.dump({str(k): v for k, v in sites.items()}, open(os.path.join(out, 'sites.json'), 'w'), indent=0)
print('instrumented stores: %d (fns: %s)' % (inst, ','.join(sorted(FNS))), file=sys.stderr)
