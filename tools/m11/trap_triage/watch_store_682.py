#!/usr/bin/env python3
"""watch_store_682.py (#682): boot_final3.ll の全 store 命令の直後に m11_sw(addr, site) を入れた build 用 IR を作る (動作は IR と同一の読み取り計装).
  usage: watch_store_682.py [--src work/boot_final3.ll] [--out work/probe682]
  生成: <out>/boot_sw.ll (IR) と <out>/sites.json (site id -> {fn, line, store 文})。
  m11_sw (trap_triage/watch_store_682.c) は [registry g = [0x11f26a0]] の [[g+8]+8] (= TList の FItems 位置) への書込みだけを
  stderr に出す: `[sw] site=<id> addr=<書込み先> w=<監視番地> val=<書込み後の 4B 値> hit=<通算>`。
  site は IR の store の位置なので、書込みを行った関数・IR 行が sites.json で引ける (値の由来は別途。stack 配置には依らない)。
  計装は call の追加のみ (IR の値・分岐は不変)。ptr 操作数が %name / @name / inttoptr 定数 / null の store だけを対象 (他は skip 数を出す)。"""
import json, os, re, sys

args = sys.argv[1:]
def opt(name, dflt):
    return args[args.index(name) + 1] if name in args else dflt
HERE = os.path.dirname(os.path.abspath(__file__)); M11 = os.path.join(HERE, '..')
src_path = opt('--src', os.path.join(M11, 'work', 'boot_final3.ll'))
out = opt('--out', os.path.join(M11, 'work', 'probe682'))
os.makedirs(out, exist_ok=True)

STORE = re.compile(r'^(\s*)store (.*), ptr (nonnull )?(%[-a-zA-Z$._0-9]+|@[-a-zA-Z$._0-9"]+|inttoptr \(i64 (-?\d+) to ptr\)|null)(, align \d+)?\s*$')
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')

def value_i32(vs, sid, ind, out_lines):
    """store の値 (`<ty> <op>`) を i32 の SSA 値 / 定数にする (整数・ptr 以外は 0)."""
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
skipped = 0
inst = 0
for ln, line in enumerate(lines, 1):
    m = DEF.match(line)
    if m:
        fn = m.group(1)
    out_lines.append(line)
    if not line.startswith(' ') or not line.lstrip().startswith('store '):
        continue
    sm = STORE.match(line)
    if not sm:
        skipped += 1
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
    out_lines.append('%scall void @m11_sw(i32 %s, i32 %s, i32 %d)' % (ind, a, v, sid))
    inst += 1
out_lines.append('declare void @m11_sw(i32, i32, i32)')
open(os.path.join(out, 'boot_sw.ll'), 'w').write('\n'.join(out_lines))
json.dump({str(k): v for k, v in sites.items()}, open(os.path.join(out, 'sites.json'), 'w'), indent=0)
print('instrumented stores: %d (skipped non-matching store lines: %d)' % (inst, skipped), file=sys.stderr)
