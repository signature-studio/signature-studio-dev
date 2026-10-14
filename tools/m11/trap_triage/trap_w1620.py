#!/usr/bin/env python3
"""trap_w1620.py (#1620): 監視番地 W への「上書き元」を、C 関数呼出しを使わずに捕まえる IR 計装。
  W の下位 4B が OLD (既定 0x1029e5d8, unit 477 直前の値) で、store 範囲が W と重なるとき、その store を
  site 固有の OOB アドレス (0xE0000000 + site) への volatile load に差し替える。
  → trap の wasm 位置から site を引く処理は未実装 (sites_trap.json に wasm 位置は無い)。計装は select と load だけで C 呼出しを含まない
     (watch_store_682.py の m11_sw 呼出しは unit 304 の結果を変えた: REPORT_1046 §20)。
  usage: trap_w1620.py [--src work/boot_final3.ll] [--out work/probe1620] [--w 0x10a9f910] [--old 0x1029e5d8]
  出力: <out>/boot_trap.ll と <out>/sites_trap.json (site -> {fn, line, store})。"""
import json, os, re, sys

args = sys.argv[1:]
def opt(name, dflt):
    return args[args.index(name) + 1] if name in args else dflt
HERE = os.path.dirname(os.path.abspath(__file__)); M11 = os.path.join(HERE, '..')
src_path = opt('--src', os.path.join(M11, 'work', 'boot_final3.ll'))
out = opt('--out', os.path.join(M11, 'work', 'probe1620'))
W = int(opt('--w', '0x10a9f910'), 0)
OLD = int(opt('--old', '0x1029e5d8'), 0)
os.makedirs(out, exist_ok=True)

STORE = re.compile(r'^(\s*)store (.*), ptr (nonnull )?(%[-a-zA-Z$._0-9]+|@[-a-zA-Z$._0-9"]+|inttoptr \(i64 (-?\d+) to ptr\)|null)(, align \d+)?\s*$')
STORE_ANY = re.compile(r'^\s*store ')
DEF = re.compile(r'^define [^\n@]*@([-a-zA-Z$._0-9"]+)\(')
WIDTH = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'ptr': 4, 'float': 4, 'double': 8}

lines = open(src_path).read().split('\n')
outl = []; fn = '?'; site = 0; sites = {}; unmatched = 0
for ln, line in enumerate(lines, 1):
    m = DEF.match(line)
    if m: fn = m.group(1)
    s = STORE.match(line)
    if not s and STORE_ANY.match(line): unmatched += 1
    if not s or fn == '?':
        outl.append(line); continue
    ind, vs, ptr = s.group(1), s.group(2), s.group(4)
    width = WIDTH.get(vs.partition(' ')[0], 16)
    k = site; site += 1
    sites[k] = {'fn': fn, 'line': ln, 'store': line.strip()[:160]}
    p = f'%wl{k}.p'
    outl += [
        f'{ind}{p} = ptrtoint ptr {ptr} to i64',
        f'{ind}%wl{k}.o = load i32, ptr inttoptr (i64 {W} to ptr), align 4',
        f'{ind}%wl{k}.a = icmp eq i32 %wl{k}.o, {OLD}',
        f'{ind}%wl{k}.b = icmp ule i64 {p}, {W + 3}',
        f'{ind}%wl{k}.c = icmp ugt i64 {p}, {W - width}',
        f'{ind}%wl{k}.d = and i1 %wl{k}.a, %wl{k}.b',
        f'{ind}%wl{k}.e = and i1 %wl{k}.d, %wl{k}.c',
        f'{ind}%wl{k}.t = select i1 %wl{k}.e, ptr inttoptr (i64 {0xE0000000 + k} to ptr), ptr {ptr}',
        f'{ind}%wl{k}.v = load volatile i8, ptr %wl{k}.t, align 1',
        line,
    ]
open(os.path.join(out, 'boot_trap.ll'), 'w').write('\n'.join(outl))
json.dump(sites, open(os.path.join(out, 'sites_trap.json'), 'w'), indent=1)
print(f'trap sites: {site} (unmatched store lines: {unmatched}; 計装されない store)')
