#!/usr/bin/env python3
"""CPUID 偽装 (SSE2 固定) の下で、export / エントリポイントから VEX 命令へ到達できるかを命令単位の CFG で数える (#540 AC5)。

前提 (lift 鎖の CPUID 実装 = tools/plugins/lift/passes/m11_simd2.py の CPUID_BODY / xgetbv): cpuid は SSE2 までしか
広告せず、xgetbv は 0 を返す。 engine / CRT の ISA 判定 (cpuid 含む関数が書く global) はこれを受けて非 AVX 側に倒れる。
本スクリプトはその結果を次の 2 slot の固定値として与え、固定値で評価できる `cmp [slot], imm; jcc` だけ不採用の辺を落とす:
  FLAG  0x180277ae4 = 0  (AVX 使用可否。 cpuid(1).ecx の OSXSAVE/AVX/FMA と xgetbv で 1 になる。 0x1801fcf98 の書込み)
  LEVEL 0x18026e018 = 1  (ISA 段階。 0x1801cd340 が AVX2 段階で 3 を書く。 SSE2 段階は 1)
それ以外の分岐は両方の辺を残す (保守的: 到達集合は過大評価側)。

usage: vex_pin.py <block> [--pin=none|sse] [--indirect=stored|all|none] [--list] [--dump-vex] [--probe=<hex,...> [--path]]   (環境変数 FL_WIN64_DIR を使う)
  --pin=none: 固定しない (全辺。 AVX 段階の下で到達できる集合)。  --pin=sse: 上の 2 slot を固定。
  switch のジャンプテーブル (lea 基底 + add + mov [基底+I*4+D]) は飛び先を解く (上限 cmp が無い場合は関数内に収まるエントリを読む)。
  解けない間接 jmp は同一関数内の全命令へ、間接 call はデータ内の関数ポインタ全体 (stored) か全関数 (all) か無し (none) へ辺を張る。 stored/all は過大評価側。
"""
import os, sys, struct, collections, bisect
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM
from capstone.x86 import X86_OP_MEM, X86_REG_RIP, X86_OP_REG as _XOR
X86_REG_T = _XOR

b = int(sys.argv[1])
pin = 'sse' if '--pin=sse' in sys.argv else 'none'
PINNED = {0x180277ae4: 0, 0x18026e018: 1} if pin == 'sse' else {}
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


def rd(va, n):
    for s in pe.sections:
        lo = base + s.VirtualAddress
        if lo <= va and va + n <= lo + s.Misc_VirtualSize:
            return s.get_data()[va - lo:va - lo + n]
    return b''


def jump_table_targets(ins, i, lo, hi):
    # `jmp R` の直前 16 命令内の `add R, B` / `mov R32, dword ptr [B + I*4 + D]` / `cmp I, N` / `lea B, [rip+X]` から
    # switch の飛び先 (B + int32 entry, entry は 0..N) を解く。 解けなければ None (呼出し側は過大評価に戻す)。
    R = ins[i].op_str
    R32 = R + 'd' if R[1:].isdigit() else 'e' + R[1:]
    win = ins[max(0, i - 16):i]
    B = tbl = bound = None
    for x in reversed(win):
        ops = x.op_str.split(', ')
        if B is None and x.mnemonic == 'add' and len(ops) == 2 and ops[0] == R:
            B = ops[1]
        elif tbl is None and x.mnemonic == 'mov' and B is not None and len(ops) == 2 and ops[0] == R32 and 'dword ptr [' in ops[1]:
            tbl = ops[1]
        elif tbl is not None and bound is None and x.mnemonic == 'cmp' and len(x.operands) == 2 and x.operands[1].type == CS_OP_IMM:
            bound = x.operands[1].imm
    if B is None or tbl is None:
        return None
    base_v = None
    for x in reversed(ins[:i]):
        if x.mnemonic == 'lea' and x.op_str.startswith(B + ', [rip') and x.operands[1].type == X86_OP_MEM:
            base_v = x.address + x.size + x.operands[1].mem.disp
            break
    if base_v is None:
        return None
    body = tbl[tbl.index('[') + 1:tbl.index(']')]
    last = body.split('+')[-1].strip()
    if not last.startswith('0x'):
        return None
    disp = int(last, 16)
    out = set()
    k = 0
    while k < 512 and (bound is None or k <= bound):
        ent = rd(base_v + disp + 4 * k, 4)
        if len(ent) != 4:
            return None
        t = base_v + struct.unpack('<i', ent)[0]
        if bound is None and not (lo <= t < hi):
            break
        out.add(t)
        k += 1
    return out or None


slot_fn = collections.defaultdict(set)
for s in data_secs:
    lo = base + s.VirtualAddress
    d = s.get_data()[:s.Misc_VirtualSize]
    for off in range(0, len(d) - 7, 8):
        v = struct.unpack_from('<Q', d, off)[0]
        if v in fset:
            slot_fn[lo + off].add(v)

IND = 'all' if '--indirect=all' in sys.argv else 'none' if '--indirect=none' in sys.argv else 'stored'
indirect_targets = fset if IND == 'all' else set().union(*slot_fn.values()) if (IND == 'stored' and slot_fn) else set()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
JCC_OPS = {  # mnemonic -> (cond(v, k)) for 符号なし/符号付きの同値 (値は非負の小整数)
    'je': lambda v, k: v == k, 'jz': lambda v, k: v == k,
    'jne': lambda v, k: v != k, 'jnz': lambda v, k: v != k,
    'jb': lambda v, k: v < k, 'jnae': lambda v, k: v < k, 'jl': lambda v, k: v < k, 'jnge': lambda v, k: v < k,
    'jae': lambda v, k: v >= k, 'jnb': lambda v, k: v >= k, 'jge': lambda v, k: v >= k, 'jnl': lambda v, k: v >= k,
    'jbe': lambda v, k: v <= k, 'jna': lambda v, k: v <= k, 'jle': lambda v, k: v <= k, 'jng': lambda v, k: v <= k,
    'ja': lambda v, k: v > k, 'jnbe': lambda v, k: v > k, 'jg': lambda v, k: v > k, 'jnle': lambda v, k: v > k,
}
insn = {}   # addr -> (mnemonic, succs(list of addr), callees(list of addr), is_vex)
vexaddr = set()
for lo, hi in funcs:
    ins = list(md.disasm(raw(lo)[:hi - lo], lo))
    idx = {x.address: i for i, x in enumerate(ins)}
    for i, x in enumerate(ins):
        nxt = ins[i + 1].address if i + 1 < len(ins) else None
        m = x.mnemonic
        succ = []
        callees = set()
        is_vex = m.startswith('v') and m not in ('verr', 'verw', 'vmcall')
        if is_vex:
            vexaddr.add(x.address)
        if m.startswith('j') and m != 'jmp' and x.operands and x.operands[0].type == CS_OP_IMM:
            t = x.operands[0].imm
            taken, fall = True, True
            prev = ins[i - 1] if i > 0 else None
            if prev and prev.mnemonic == 'cmp' and len(prev.operands) == 2 and prev.operands[0].type == X86_OP_MEM \
                    and prev.operands[0].mem.base == X86_REG_RIP and prev.operands[1].type == CS_OP_IMM \
                    and prev.address + prev.size + prev.operands[0].mem.disp in PINNED and m in JCC_OPS:
                slot = prev.address + prev.size + prev.operands[0].mem.disp
                r = JCC_OPS[m](PINNED[slot], prev.operands[1].imm)
                taken, fall = r, not r
            if taken:
                succ.append(t)
            if fall and nxt is not None:
                succ.append(nxt)
        elif m == 'jmp' and x.operands and x.operands[0].type == CS_OP_IMM:
            succ.append(x.operands[0].imm)
        elif m == 'jmp':
            jt = jump_table_targets(ins, i, lo, hi) if x.operands and x.operands[0].type == X86_REG_T else None
            if jt is not None:
                succ.extend(sorted(jt))
            else:
                succ.extend(a.address for a in ins)
        elif m in ('ret', 'retq', 'int3', 'ud2', 'hlt'):
            pass
        else:
            if m == 'call':
                if x.operands and x.operands[0].type == CS_OP_IMM:
                    t = owner(x.operands[0].imm)
                    if t is not None:
                        callees.add(t)
                elif x.operands and x.operands[0].type == X86_OP_MEM and x.operands[0].mem.base == X86_REG_RIP:
                    tg = x.address + x.size + x.operands[0].mem.disp
                    for f in slot_fn.get(tg, ()):
                        callees.add(f)
                else:
                    callees.update(indirect_targets)
            if nxt is not None:
                succ.append(nxt)
        for op in x.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tg = x.address + x.size + op.mem.disp
                if tg in fset and m != 'call':
                    callees.add(tg)
                for f in slot_fn.get(tg, ()):
                    if m != 'call':
                        callees.add(f)
        insn[x.address] = (m, succ, callees)
roots = set()
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
for ex in (pe.DIRECTORY_ENTRY_EXPORT.symbols if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT') else []):
    if ex.address:
        t = owner(base + ex.address)
        if t is not None:
            roots.add(t)
ep = owner(base + pe.OPTIONAL_HEADER.AddressOfEntryPoint)
if ep is not None:
    roots.add(ep)
seen = set(roots)
q = collections.deque(roots)
par = {}
while q:
    a = q.popleft()
    if a not in insn:
        continue
    m, succ, callees = insn[a]
    for y in list(succ) + list(callees):
        if y not in seen:
            seen.add(y); q.append(y); par[y] = a
vex_reached = vexaddr & seen
vex_funcs = set()
for a in vex_reached:
    i = bisect.bisect_right(starts, a) - 1
    vex_funcs.add(starts[i])
print('block=%d pin=%s indirect=%s roots=%d reached_insn=%d vex_insn_total=%d vex_insn_reached=%d vex_funcs_reached=%d' % (
    b, pin, IND, len(roots), len(seen), len(vexaddr), len(vex_reached), len(vex_funcs)))
PROBE = [a for a in sys.argv if a.startswith('--probe=')]
for a in [int(x, 16) for x in PROBE[0][len('--probe='):].split(',')] if PROBE else []:
    print('probe 0x%x reached=%s' % (a, a in seen))
    if a in seen and '--path' in sys.argv:
        chain = [a]
        while chain[-1] in par and len(chain) < 40:
            chain.append(par[chain[-1]])
        print('  path: ' + ' <- '.join('0x%x(%s)' % (c, insn[c][0] if c in insn else '?') for c in chain))
if '--dump-vex' in sys.argv:
    for a in sorted(vex_reached):
        print('  reached vex 0x%x fn 0x%x' % (a, owner(a)))
if '--list' in sys.argv:
    for f in sorted(vex_funcs):
        print('0x%x vex=%d' % (f, sum(1 for a in vex_reached if owner(a) == f)))
