#!/usr/bin/env python3
"""x64 PE: .pdata 関数境界 + capstone による direct-call closure。
usage: closure.py <pe> <root-va-hex>[,<root-va-hex>...] [--maxdepth N] [--json out.json]
 - call rel32 / jmp rel32 (関数外) を辿り、関数数・バイト数・SIMD命令数・間接呼出/IAT呼出を集計
 - vtable 参照 (lea reg,[rip+vtable]) を持つ ctor 探索: --find-vref <va-hex>
"""
import sys, re, struct, json, argparse, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP, X86_OP_IMM

ap = argparse.ArgumentParser()
ap.add_argument('pe'); ap.add_argument('roots', nargs='?', default='')
ap.add_argument('--maxdepth', type=int, default=99)
ap.add_argument('--json'); ap.add_argument('--find-vref', action='append', default=[])
ap.add_argument('--stop', default='', help='comma list of VA (hex) not to descend into')
a = ap.parse_args()

pe = pefile.PE(a.pe)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.__data__
pd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
raw = pe.get_data(pd.VirtualAddress, pd.Size)
funcs = []
_ents = []
for i in range(len(raw) // 12):
    b, e, u = struct.unpack_from('<III', raw, i * 12)
    _ents.append((b, e, (pe.get_data(u & ~1, 1)[0] >> 3) & 4))
_ents.sort()
# UNW_FLAG_CHAININFO(4) の連続チャンクを親関数へ併合 (MSVC shrink-wrap 分割: 例 prologue 7B + 本体)
for b, e, ch in _ents:
    if ch and funcs and funcs[-1][1] == b:
        funcs[-1] = (funcs[-1][0], e)
    else:
        funcs.append((b, e))
starts = [b for b, e in funcs]
import bisect
def func_of(rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i >= 0 and funcs[i][0] <= rva < funcs[i][1]:
        return funcs[i]
    return None
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
T0, T1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
tdata = pe.get_data(T0, text.Misc_VirtualSize)

iat = {}
if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
    for imp in pe.DIRECTORY_ENTRY_IMPORT:
        for i in imp.imports:
            iat[i.address - base] = imp.dll.decode().lower() + '!' + (i.name.decode() if i.name else str(i.ordinal))

# ---- vtable refs
for v in a.find_vref:
    tgt = int(v, 16) - base
    hits = []
    for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', tdata):
        p = m.start()
        disp = struct.unpack_from('<i', tdata, p + 3)[0]
        t = T0 + p + 7 + disp
        if t == tgt:
            f = func_of(T0 + p)
            hits.append((hex(base + T0 + p), hex(base + f[0]) if f else None, (f[1] - f[0]) if f else None))
    print('vref', v, hits)

md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True

SIMD_PFX = ('p', 'v', 'mov', 'add', 'sub', 'mul', 'div', 'sqrt', 'max', 'min', 'cvt', 'unpck', 'shuf', 'and', 'or', 'xor', 'cmp', 'rcp', 'rsqrt', 'comis', 'ucomis', 'round', 'hadd', 'blend', 'movs')
def is_sse(m, ops):
    if m.endswith(('ss', 'sd', 'ps', 'pd')) and not m.startswith(('j', 'cmov', 'set')) and m not in ('movss', 'movsd') or m.startswith(('v', 'pshuf', 'punpck', 'padd', 'psub', 'pmul', 'pand', 'por', 'pxor', 'pcmp', 'pmov', 'psra', 'psrl', 'psll', 'cvt', 'unpck', 'movap', 'movup', 'movdq', 'movq', 'movd')):
        return True
    return False

def analyze(rva, size):
    code = tdata[rva - T0: rva - T0 + size]
    info = {'n': 0, 'sse': 0, 'calls': set(), 'indcalls': 0, 'iat': collections.Counter(), 'rip_refs': 0}
    for ins in md.disasm(code, base + rva):
        info['n'] += 1
        m = ins.mnemonic
        if is_sse(m, None): info['sse'] += 1
        if m in ('call', 'jmp') and ins.operands:
            op = ins.operands[0]
            if op.type == X86_OP_IMM:
                t = op.imm - base
                f = func_of(t)
                if f and f[0] != rva:
                    info['calls'].add(f[0])
                elif not f and T0 <= t < T1:
                    info['calls'].add(t)  # thunk w/o pdata
            elif op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp - base
                if t in iat: info['iat'][iat[t]] += 1
                else: info['indcalls'] += 1
            elif m == 'call':
                info['indcalls'] += 1
    return info

if a.roots:
    roots = [int(x, 16) - base for x in a.roots.split(',')]
    stop = {int(x, 16) - base for x in a.stop.split(',') if x}
    seen, order, depth = {}, [], {}
    q = collections.deque((r, 0) for r in roots)
    while q:
        r, d = q.popleft()
        if r in seen: continue
        f = func_of(r)
        size = (f[1] - f[0]) if f else 16
        if f: r = f[0]
        if r in seen: continue
        info = analyze(r, size)
        seen[r] = (size, info); depth[r] = d; order.append(r)
        if r in stop or d >= a.maxdepth: continue
        for c in info['calls']:
            if c not in seen: q.append((c, d + 1))
    tot_b = sum(s for s, _ in seen.values()); tot_i = sum(i['n'] for _, i in seen.values()); tot_s = sum(i['sse'] for _, i in seen.values())
    iat_tot = collections.Counter()
    for _, i in seen.values(): iat_tot.update(i['iat'])
    print('closure funcs=%d bytes=%d insns=%d sse_insns=%d (%.1f%%) indirect_calls=%d' % (len(seen), tot_b, tot_i, tot_s, 100.0 * tot_s / max(1, tot_i), sum(i['indcalls'] for _, i in seen.values())))
    print('IAT calls:', dict(iat_tot))
    big = sorted(((s, hex(base + r), depth[r]) for r, (s, _) in seen.items()), reverse=True)[:25]
    print('largest:', big)
    if a.json:
        json.dump({'roots': a.roots, 'funcs': [{'va': hex(base + r), 'size': seen[r][0], 'depth': depth[r], 'insns': seen[r][1]['n'], 'sse': seen[r][1]['sse'],
                   'calls': [hex(base + c) for c in sorted(seen[r][1]['calls'])], 'indcalls': seen[r][1]['indcalls'], 'iat': dict(seen[r][1]['iat'])} for r in order]}, open(a.json, 'w'), indent=1)
