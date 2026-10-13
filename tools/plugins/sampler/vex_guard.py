#!/usr/bin/env python3
"""engine / 単体 DLL の .pdata 関数ごとに VEX 命令 (v 始まりの SSE/AVX mnemonic)・cpuid・xgetbv の有無を数え、
VEX を含む関数が cpuid/xgetbv を持つ関数から (直接 call で) 到達されるかを調べる。 CPUID 分岐で SSE 路に固定できるかの静的な下調べ。
usage: vex_guard.py <block>   → stdout: 1 行サマリ + 関数一覧 (--list)
"""
import os, sys, struct, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_CALL
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
code_secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
def raw(va):
    for s in code_secs:
        lo = base + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return s.get_data()[va - lo:]
    return b''
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
info = {}
calls = collections.defaultdict(set)
import bisect
def owner(va):
    i = bisect.bisect_right(starts, va) - 1
    return funcs[i][0] if i >= 0 and funcs[i][0] <= va < funcs[i][1] else None
for lo, hi in funcs:
    vex = cpuid = xg = 0
    for ins in md.disasm(raw(lo)[:hi - lo], lo):
        m = ins.mnemonic
        if m.startswith('v') and m not in ('verr', 'verw', 'vmcall'):
            vex += 1
        elif m == 'cpuid':
            cpuid += 1
        elif m == 'xgetbv':
            xg += 1
        elif m in ('call', 'jmp') and ins.op_str.startswith('0x'):
            t = owner(int(ins.op_str, 16))
            if t and t != lo:
                calls[lo].add(t)
    info[lo] = (vex, cpuid, xg)
vexf = {f for f, v in info.items() if v[0]}
guard = {f for f, v in info.items() if v[1] or v[2]}
rev = collections.defaultdict(set)
for a, bs in calls.items():
    for t in bs:
        rev[t].add(a)
# VEX 関数の直接 caller を遡り、caller 鎖のどこかに cpuid / xgetbv 関数があるか (深さ 3)
def reach_guard(f, depth=3):
    seen, front = {f}, {f}
    for _ in range(depth):
        nxt = set()
        for x in front:
            for c in rev.get(x, ()):
                if c not in seen:
                    seen.add(c); nxt.add(c)
        front = nxt
        if seen & guard:
            return True
    return False
nv = sum(info[f][0] for f in vexf)
print('block=%d pdata_funcs=%d vex_funcs=%d vex_insns=%d cpuid_funcs=%d xgetbv_funcs=%d vex_funcs_with_guard_caller_depth3=%d vex_funcs_without=%d' % (
    b, len(funcs), len(vexf), nv, sum(1 for v in info.values() if v[1]), sum(1 for v in info.values() if v[2]),
    sum(1 for f in vexf if reach_guard(f)), sum(1 for f in vexf if not reach_guard(f))))
if '--list' in sys.argv:
    for f in sorted(vexf):
        print('0x%x vex=%d size=%d guard=%s' % (f, info[f][0], dict(funcs)[f] - f, reach_guard(f)))
