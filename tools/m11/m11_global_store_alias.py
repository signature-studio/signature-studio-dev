#!/usr/bin/env python3
"""書込可能グローバル VA への store を、IR の SSA ポインタ連鎖で数える (#5449 / M11-N244 / 親 #4906).

store のポインタを後ろ向きに辿り、実効アドレス (定数 inttoptr の値 + GEP の定数 offset) を求める。
  - inttoptr (定数) / getelementptr (inbounds・定数式を含む・定数 index のみ) / bitcast / phi (全入力が同じ結果)
  - 実効アドレスが定まったら、store のサイズと 対象 VA から --span バイト (既定 8) の区間との重なりで判定する
    - va_hit     : 重なる (対象 VA への store)
    - const_other: 定数アドレスだが重ならない
  - 定まらないものは理由別に数える:
    - alloca          : reg2mem スロット (load 経由ではない alloca)。メモリ SSA が無いので辿らない (未決)
    - load_ptr        : ポインタを load で得たもの (別名解析が無いため追えない)
    - const_var_offset: 定数 inttoptr が基底だが GEP の index が非定数
    - gep_unsupported : GEP の型が配列・スカラー以外、または型サイズ不明
    - size_unknown    : store の値型のサイズが不明
    - unknown         : 上記以外 (引数・call 戻り値・非定数 inttoptr・算術など)
出力は件数のみ (IR は変更しない)。値の到達定義 (格納値) は別件 (未実装)。

使い方: python3 m11_global_store_alias.py boot_final.ll [--va 0x15e3a70] [--span 8] [--out result.json]
"""
import argparse, collections, json, re

ap = argparse.ArgumentParser()
ap.add_argument('ir')
ap.add_argument('--va', default='0x15e3a70')
ap.add_argument('--span', type=int, default=8)
ap.add_argument('--out')
ap.add_argument('--depth', type=int, default=12)
args = ap.parse_args()
TARGET = int(args.va, 16)

DEF = re.compile(r'^\s*(%[^\s=]+)\s*=\s*(.*)$')
CONST_PTR = re.compile(r'^(?:inttoptr \(i64 (\d+) to ptr\)|inttoptr i64 (\d+) to ptr)$')
ARRAY = re.compile(r'^\[(\d+) x (.+)\]$')
IDX = re.compile(r'^i\d+\s+(-?\d+)$')
PHI_VAL = re.compile(r'\[\s*([^,\]]+?)\s*,')
OPERAND = re.compile(r'%[A-Za-z0-9_.$-]+')

defs = {}
funcs = []
with open(args.ir, 'r', errors='replace') as f:
    for line in f:
        if line.startswith('define '):
            defs = {}
            funcs.append((defs, []))
            continue
        if not funcs:
            funcs.append((defs, []))
        m = DEF.match(line)
        if m:
            defs[m.group(1)] = m.group(2).rstrip()
            continue
        if re.match(r'^\s*store\s', line):
            funcs[-1][1].append(line.rstrip('\n'))
stores = [(fd, s) for fd, ss in funcs for s in ss]

def top_level_parts(s):
    parts, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    parts.append(cur.strip())
    return parts

def split_type(s):
    depth = 0
    for i, ch in enumerate(s):
        if ch in '[{<(':
            depth += 1
        elif ch in ']})>':
            depth -= 1
        elif ch.isspace() and depth == 0:
            return s[:i]
    return s

def tsize(t):
    t = t.strip()
    m = re.fullmatch(r'i(\d+)', t)
    if m:
        return max(1, (int(m.group(1)) + 7) // 8)
    if t == 'ptr' or t == 'double':
        return 8
    if t in ('float', 'i32'):
        return 4
    if t == 'half':
        return 2
    m = ARRAY.match(t)
    if m:
        e = tsize(m.group(2))
        return None if e is None else int(m.group(1)) * e
    return None

def idx_const(s):
    m = IDX.match(s.strip())
    return int(m.group(1)) if m else None

def gep_offset(src, idx):
    """定数 offset (int) / 非定数 index 'var' / 扱えない None。"""
    if not idx:
        return None
    size = tsize(src)
    if size is None:
        return None
    first = idx_const(idx[0])
    if first is None:
        return 'var' if re.match(r'^i\d+\s', idx[0]) else None
    off, cur = first * size, src.strip()
    for ip in idx[1:]:
        m = ARRAY.match(cur)
        if not m:
            return None
        k = idx_const(ip)
        if k is None:
            return 'var' if re.match(r'^i\d+\s', ip) else None
        esz = tsize(m.group(2))
        if esz is None:
            return None
        off += k * esz
        cur = m.group(2).strip()
    return off

def resolve_ssa(name, depth, seen):
    if name in seen:
        return ('kind', 'cycle')
    if name not in defs:
        return ('kind', 'unknown')
    seen = seen | {name}
    d = defs[name]
    if re.match(r'^alloca\b', d):
        return ('kind', 'alloca')
    if re.match(r'^load\b', d):
        return ('kind', 'load_ptr')
    return resolve(d, depth, seen)

def resolve_gep(e, depth, seen):
    body = re.sub(r'^getelementptr\s+', '', e)
    body = re.sub(r'^((?:inbounds|nuw|nusw)\s+)+', '', body)
    if body.startswith('('):
        if not body.endswith(')'):
            return ('kind', 'unknown')
        body = body[1:-1]
    parts = top_level_parts(body)
    if len(parts) < 2 or not parts[1].startswith('ptr '):
        return ('kind', 'unknown')
    off = gep_offset(parts[0], parts[2:])
    base = resolve(parts[1][len('ptr '):].strip(), depth + 1, seen)
    if base[0] != 'const':
        return base
    if isinstance(off, int):
        return ('const', base[1] + off)
    return ('kind', 'const_var_offset' if off == 'var' else 'gep_unsupported')

def resolve(expr, depth, seen):
    """('const', 実効アドレス) または ('kind', 理由)。"""
    if depth > args.depth:
        return ('kind', 'depth_limit')
    if expr is None:
        return ('kind', 'unknown')
    e = expr.strip()
    if e.startswith('%'):
        return resolve_ssa(e, depth + 1, seen)
    m = CONST_PTR.match(e)
    if m:
        return ('const', int(m.group(1) or m.group(2)))
    if e.startswith('getelementptr'):
        return resolve_gep(e, depth, seen)
    if e.startswith('bitcast'):
        ops = OPERAND.findall(e)
        return resolve_ssa(ops[0], depth + 1, seen) if ops else ('kind', 'unknown')
    if e.startswith('phi'):
        res = [resolve(v, depth + 1, seen) for v in PHI_VAL.findall(e)]
        if res and all(r == res[0] for r in res):
            return res[0]
        return ('kind', 'phi_mixed')
    return ('kind', 'unknown')

def ptr_of_store(line):
    parts = top_level_parts(line.strip()[len('store '):])
    if len(parts) < 2 or not parts[1].startswith('ptr '):
        return None
    return parts[1][len('ptr '):].strip()

def store_value_type(line):
    return split_type(top_level_parts(line.strip()[len('store '):])[0])

def store_class(line):
    p = ptr_of_store(line)
    if p is None:
        return 'no_ptr'
    r = resolve(p, 0, frozenset())
    if r[0] != 'const':
        return r[1]
    size = tsize(store_value_type(line))
    if size is None:
        return 'size_unknown'
    a = r[1]
    return 'va_hit' if a < TARGET + args.span and TARGET < a + size else 'const_other'

counts = collections.Counter()
unknown_head = collections.Counter()
for fd, s in stores:
    defs = fd
    c = store_class(s)
    counts[c] += 1
    p = ptr_of_store(s)
    if c == 'unknown' and p and p.startswith('%'):
        d = defs.get(p, '<param/undefined>')
        unknown_head[re.split(r'[\s(]', d)[0] or '<empty>'] += 1

total = len(stores)
print('[global-store-alias] target VA %s span %d  IR store 行 %d' % (hex(TARGET), args.span, total))
for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
    print('  %-16s %d' % (k, v))
print('[unknown の定義元の内訳 (上位 8)]')
for k, v in unknown_head.most_common(8):
    print('  %-14s %d' % (k, v))
if args.out:
    json.dump({'va': hex(TARGET), 'span': args.span, 'stores': total, 'counts': counts,
               'unknown_head': unknown_head}, open(args.out, 'w'), indent=1, default=str)
