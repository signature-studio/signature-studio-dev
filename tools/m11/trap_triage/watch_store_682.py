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
only = set(opt('--fns', '').split(',')) - {''}   # #2270: 指定時はこの関数の store だけ計装する (他は素通し)
if '--fns-file' in args:   # #2408: 関数名 1 行 1 件のファイル (14,881 関数の名前は引数長の上限 128 KiB を超える)
    only |= set(open(opt('--fns-file', '')).read().split()) - {''}
os.makedirs(out, exist_ok=True)

STORE = re.compile(r'^(\s*)store (.*), ptr (nonnull )?(%[-a-zA-Z$._0-9]+|@[-a-zA-Z$._0-9"]+|inttoptr \(i64 (-?\d+) to ptr\)|null)(, align \d+)?\s*$')
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')

WIDTH = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'ptr': 4, 'float': 4, 'double': 8}
def store_width(vs):
    """store の値型から書込み幅 (byte) を出す. 未知の型 (ベクタ等) は 16 (広めに取り取りこぼしを避ける)."""
    ty = vs.partition(' ')[0]
    return WIDTH.get(ty, 16)

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
# #2769: ALLOCA_SKIP=1 のとき、alloca で作ったスタックスロットを直接指す store を計装しない (既定 0)。
#   スロットのアドレスを ptrtoint で外に出すと、空の hook でも lift 済み関数の終了条件が変わり無限 loop になった (REPORT_1783 §8)。
#   0x1ac308 はイメージ内の番地でスタック (alloca) には届かないため、監視対象から外しても取りこぼしは無い。
ALLOCA_SKIP = os.environ.get('ALLOCA_SKIP') == '1'
ALLOCAS = {}
_cur = None
for _l in lines:
    _m = DEF.match(_l)
    if _m:
        _cur = _m.group(1)
    _a = re.match(r'^\s*%([-a-zA-Z$._0-9]+) = alloca', _l)
    if _a and _cur:
        ALLOCAS.setdefault(_cur, set()).add(_a.group(1))
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
    if only and fn not in only:
        continue
    sm = STORE.match(line)
    if not sm:
        skipped += 1
        continue
    if ALLOCA_SKIP and sm.group(4).startswith('%') and sm.group(4)[1:] in ALLOCAS.get(fn, ()):
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
    out_lines.append('%scall void @m11_sw(i32 %s, i32 %s, i32 %d, i32 %d)' % (ind, a, v, sid, store_width(sm.group(2))))
    inst += 1
out_lines.append('declare void @m11_sw(i32, i32, i32, i32)')
open(os.path.join(out, 'boot_sw.ll'), 'w').write('\n'.join(out_lines))
json.dump({str(k): v for k, v in sites.items()}, open(os.path.join(out, 'sites.json'), 'w'), indent=0)
print('instrumented stores: %d (skipped non-matching store lines: %d)' % (inst, skipped), file=sys.stderr)
