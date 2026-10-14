#!/usr/bin/env python3
"""VEX を含む .pdata 関数が、export / エントリポイントから cpuid・xgetbv を通らずに到達できるかを調べる (#540 AC5)。

vex_guard.py は直接 call の深さ 3 しか見ないため、ここでは辺を次の 3 種に広げる:
  1. 直接 call / jmp の即値先 (関数の内側は owner に寄せる)
  2. RIP 相対の参照先が関数先頭 (関数ポインタの取得 lea)
  3. RIP 相対の参照先がデータ内の関数ポインタ (vtable・テーブル。 8 byte 絶対 VA の一致で拾う)
判定: root から cpuid/xgetbv を含む関数を取り除いたグラフで到達できる VEX 関数を数える (= CPUID を偽装しても
通ってしまう経路がある関数)。 0 件なら CPUID 分岐で SSE 路に固定できる見込み。 1 件以上なら固定だけでは足りない。
辺 3 は over-approximation (テーブル全体を参照した関数から全要素へ辺を張る)。 4 byte RVA テーブルは未対応。

usage: vex_reach.py <block>   (環境変数 FL_WIN64_DIR を使う)
"""
import os, sys, struct, collections, bisect
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

b = int(sys.argv[1])
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b'\0'): s for s in pe.sections}
pd = sec[b'.pdata'].get_data()[:sec[b'.pdata'].Misc_VirtualSize]
funcs = []
for i in range(len(pd) // 12):
    s, e, u = struct.unpack_from('<III', pd, 12 * i)
    if s and not (u & 1) and e > s:
        funcs.append((base + s, base + e))
funcs.sort()
starts = [f[0] for f in funcs]
ends = dict(funcs)
fset = set(starts)
code_secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
data_secs = [s for s in pe.sections if not (s.Characteristics & 0x20000000) and s.Name.rstrip(b'\0') != b'.pdata']


def raw(va):
    for s in code_secs:
        lo = base + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return s.get_data()[va - lo:]
    return b''


def owner(va):
    i = bisect.bisect_right(starts, va) - 1
    return starts[i] if i >= 0 and va < ends[starts[i]] else None


# 3: データ内の関数ポインタ。 slot VA -> 関数先頭の集合
slot_fn = collections.defaultdict(set)
for s in data_secs:
    lo = base + s.VirtualAddress
    d = s.get_data()[:s.Misc_VirtualSize]
    for off in range(0, len(d) - 7, 8):
        v = struct.unpack_from('<Q', d, off)[0]
        if v in fset:
            slot_fn[lo + off].add(v)

md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
vex = {}
guard = set()
edges = collections.defaultdict(set)
for lo, hi in funcs:
    nv = 0
    gd = False
    for ins in md.disasm(raw(lo)[:hi - lo], lo):
        m = ins.mnemonic
        if m.startswith('v') and m not in ('verr', 'verw', 'vmcall'):
            nv += 1
        elif m in ('cpuid', 'xgetbv'):
            gd = True
        if m in ('call', 'jmp') and ins.operands and ins.operands[0].type == CS_OP_IMM:
            t = owner(ins.operands[0].imm)
            if t is not None and t != lo:
                edges[lo].add(t)
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in fset and tgt != lo:
                    edges[lo].add(tgt)
                for f in slot_fn.get(tgt, ()):
                    if f != lo:
                        edges[lo].add(f)
    vex[lo] = nv
    if gd:
        guard.add(lo)

vexf = {f for f, n in vex.items() if n}
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
roots = set()
for ex in (pe.DIRECTORY_ENTRY_EXPORT.symbols if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT') else []):
    if ex.address:
        t = owner(base + ex.address)
        if t is not None:
            roots.add(t)
ep = owner(base + pe.OPTIONAL_HEADER.AddressOfEntryPoint)
if ep is not None:
    roots.add(ep)
roots_nog = roots - guard


def bfs(start, banned, parent=None):
    seen = set(x for x in start if x not in banned)
    q = collections.deque(seen)
    while q:
        x = q.popleft()
        for y in edges.get(x, ()):
            if y not in seen and y not in banned:
                seen.add(y); q.append(y)
                if parent is not None:
                    parent[y] = x
    return seen


reach_all = bfs(roots, set())
par = {}
reach_nog = bfs(roots_nog, guard, par)
# 上限版: データ内に関数ポインタとして置かれた関数 (CRT 初期化テーブル・vtable 等) を全て root とみなす
stored = set().union(*slot_fn.values()) if slot_fn else set()
roots_up = (roots | stored) - guard
reach_up = bfs(roots_up, guard)
n_edges = sum(len(v) for v in edges.values())
print('block=%d pdata_funcs=%d exports+entry=%d stored_fn_ptrs=%d edges=%d guard_funcs=%d vex_funcs=%d' % (
    b, len(funcs), len(roots), len(stored), n_edges, len(guard), len(vexf)))
print('block=%d [exports+entry] reachable_all=%d vex_reachable_any=%d vex_reachable_without_guard=%d vex_unreachable=%d' % (
    b, len(reach_all), len(vexf & reach_all), len(vexf & reach_nog), len(vexf - reach_all)))
print('block=%d [upper: +stored fn ptrs] reachable_without_guard=%d vex_reachable_without_guard=%d' % (
    b, len(reach_up), len(vexf & reach_up)))
if '--list' in sys.argv:
    for f in sorted(vexf & reach_nog):
        path = [f]
        while path[-1] in par:
            path.append(par[path[-1]])
        print('0x%x vex=%d size=%d path=%s' % (f, vex[f], ends[f] - f, ' <- '.join('0x%x' % x for x in path[:6])))
