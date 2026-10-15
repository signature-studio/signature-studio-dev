#!/usr/bin/env python3
"""書込可能グローバル VA への store を、IR の SSA ポインタ連鎖で数える (#5449 / M11-N244 / 親 #4906).

対象 VA (既定 0x15e3a70) を指す定数 inttoptr から、store のポインタ被演算子までの連鎖を後ろ向きに辿る:
  inttoptr (定数) / getelementptr (inbounds 含む) / bitcast / add・sub (定数項) / phi (全入力が同じ根)
辿れた store を 対象 VA の store (direct_chain) とし、辿れないものは理由別に数える。
  - stack_slot : ポインタが reg2mem スロット (load 経由)。メモリ SSA が無いので辿らない (未決)
  - const_other: 定数 inttoptr だが別 VA
  - unknown    : 上記以外 (引数・load・call 戻り値など)
出力は件数のみ (IR は変更しない)。値の到達定義 (格納値) は別件 (未実装)。

使い方: python3 m11_global_store_alias.py boot_final.ll [--va 0x15e3a70] [--out result.json]
"""
import argparse, collections, json, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('ir')
ap.add_argument('--va', default='0x15e3a70')
ap.add_argument('--out')
ap.add_argument('--depth', type=int, default=12)
args = ap.parse_args()
TARGET = int(args.va, 16)

DEF = re.compile(r'^\s*(%[^\s=]+)\s*=\s*(.*)$')
INTTOPTR = re.compile(r'inttoptr \(i64 (\d+) to ptr\)|inttoptr i64 (\d+) to ptr')
GEP_CE = re.compile(r'getelementptr[^(]*\(\[[^\]]*\], ptr inttoptr \(i64 (\d+) to ptr\)')
OPERAND = re.compile(r'%[A-Za-z0-9_.$-]+')

defs = {}
stores = []
with open(args.ir, 'r', errors='replace') as f:
    for line in f:
        m = DEF.match(line)
        if m:
            defs[m.group(1)] = m.group(2)
            continue
        if re.match(r'^\s*store\s', line):
            stores.append(line.rstrip('\n'))

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

def ptr_of_store(line):
    body = line.strip()[len('store '):]
    parts = top_level_parts(body)
    if len(parts) < 2 or not parts[1].startswith('ptr '):
        return None
    return parts[1][len('ptr '):].strip()

def const_addr(expr):
    m = INTTOPTR.search(expr)
    if m:
        return int(m.group(1) or m.group(2))
    return None

def classify(expr, depth, seen):
    if depth > args.depth:
        return 'depth_limit'
    if expr is None:
        return 'unknown'
    a = const_addr(expr)
    if a is not None:
        return 'va_hit' if a == TARGET else 'const_other'
    m = GEP_CE.search(expr)
    if m:
        return 'va_hit' if int(m.group(1)) == TARGET else 'const_other'
    if expr.startswith('getelementptr') or expr.startswith('bitcast') or expr.startswith('add') or expr.startswith('sub'):
        ops = OPERAND.findall(expr)
        if not ops:
            return 'unknown'
        return classify_ssa(ops[0], depth + 1, seen)
    if expr.startswith('phi'):
        ops = OPERAND.findall(expr)
        res = set(classify_ssa(o, depth + 1, seen) for o in ops)
        if res == {'va_hit'}:
            return 'va_hit'
        return 'phi_mixed' if res else 'unknown'
    return 'unknown'

def classify_ssa(name, depth, seen):
    if name in seen:
        return 'cycle'
    if name not in defs:
        return 'unknown'
    seen = seen | {name}
    d = defs[name]
    if re.match(r'^alloca\b', d):
        return 'alloca'
    if re.match(r'^load\b', d):
        return 'load_ptr'
    return classify(d, depth, seen)

counts = collections.Counter()
for s in stores:
    p = ptr_of_store(s)
    if p is None:
        counts['no_ptr'] += 1
        continue
    if p.startswith('%'):
        counts[classify_ssa(p, 0, frozenset())] += 1
    else:
        counts[classify(p, 0, frozenset())] += 1

unknown_head = collections.Counter()
for s in stores:
    p = ptr_of_store(s)
    if p and p.startswith('%') and classify_ssa(p, 0, frozenset()) == 'unknown':
        d = defs.get(p, '<param/undefined>')
        unknown_head[re.split(r'[\s(]', d)[0] or '<empty>'] += 1

total = len(stores)
print('[global-store-alias] target VA %s  IR store 行 %d' % (hex(TARGET), total))
for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
    print('  %-14s %d' % (k, v))
print('[unknown の定義元の内訳 (上位 8)]')
for k, v in unknown_head.most_common(8):
    print('  %-14s %d' % (k, v))
if args.out:
    json.dump({'va': hex(TARGET), 'stores': total, 'counts': counts,
               'unknown_head': unknown_head}, open(args.out, 'w'), indent=1, default=str)
