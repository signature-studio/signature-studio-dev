#!/usr/bin/env python3
"""x87_reach.py: ILTools_x64.dll (block24347_PE.bin) の x87 命令を含む関数が、export から到達しうるかを測る (T-SH-12 #154)。
usage: x87_reach.py PE   (標準出力に集計のみ。ファイルは書かない)
  A. .pdata 全関数の x87 命令数 (f* 始まりの mnemonic) と、それを含む関数数
  B. export (.text 内) を root にした直接 call 閉包 (call rel32 のみ) の関数数・x87 関数数
  C. 閉包内の間接 call / jmp (reg・mem 経由) の数。直接 call で追えない到達の上限の目安
  D. 絶対アドレスの取得元 (DIR64 reloc の指す値が関数先頭) のうち、x87 関数を指すもの。
     関数ポインタ・VMT として間接 call で到達しうる候補
"""
import bisect, sys
import capstone, pefile

pe = pefile.PE(sys.argv[1])
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
tlo, thi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
funcs = []
for i in range(d.Size // 12):
    b, e = (int.from_bytes(img[d.VirtualAddress + 12 * i + k * 4:d.VirtualAddress + 12 * i + k * 4 + 4], 'little') for k in (0, 1))
    if tlo <= b < thi:
        funcs.append((b, e))
funcs = sorted(set(funcs))
starts = [b for b, _ in funcs]
ends = {b: e for b, e in funcs}


def fn_of(rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i >= 0 and rva < ends[starts[i]]:
        return starts[i]
    return None


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
x87_insns = {}
calls_direct = {}
indirect = {}
x87_fn = set()
code_refs = {}
for b, e in funcs:
    n87 = 0
    for ins in md.disasm(bytes(img[b:e]), base + b):
        if ins.mnemonic.startswith('f'):
            n87 += 1
        if ins.mnemonic in ('call', 'jmp'):
            op = ins.operands[0] if ins.operands else None
            if op is not None and op.type == capstone.x86.X86_OP_IMM:
                if ins.mnemonic == 'call':
                    calls_direct.setdefault(b, set()).add(op.imm - base)
            else:
                indirect[b] = indirect.get(b, 0) + 1
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                code_refs.setdefault(ins.address + ins.size + op.mem.disp - base, []).append(b)
            elif op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ('mov', 'lea', 'push'):
                code_refs.setdefault(op.imm - base, []).append(b)
    if n87:
        x87_insns[b] = n87
        x87_fn.add(b)

print('[A] pdata funcs %d / x87 insns %d / x87 funcs %d' % (len(funcs), sum(x87_insns.values()), len(x87_fn)))

roots = set()
for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if tlo <= s.address < thi:
        f = fn_of(s.address)
        if f is not None:
            roots.add(f)
def closure(rs):
    seen, todo = set(rs), list(rs)
    while todo:
        f = todo.pop()
        for t in calls_direct.get(f, ()):
            g = fn_of(t)
            if g is not None and g not in seen:
                seen.add(g)
                todo.append(g)
    return seen


seen = closure(roots)
clo_x87 = seen & x87_fn
print('[B] export roots %d / direct-call closure funcs %d / x87 funcs in closure %d / x87 insns in closure %d' % (
    len(roots), len(seen), len(clo_x87), sum(x87_insns[f] for f in clo_x87)))
ep = fn_of(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
eps = closure([ep]) if ep is not None else set()
print('[B2] entry point %s / closure funcs %d / x87 funcs in closure %d' % (
    hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint), len(eps), len(eps & x87_fn)))
print('[C] indirect call/jmp sites in closure %d (funcs with >=1: %d)' % (
    sum(indirect.get(f, 0) for f in seen), sum(1 for f in seen if indirect.get(f))))

taken = {}
for blk in pe.DIRECTORY_ENTRY_BASERELOC:
    for ent in blk.entries:
        if ent.type != 10:
            continue
        rva = ent.rva
        v = int.from_bytes(img[rva:rva + 8], 'little') - base
        if v in ends:
            taken.setdefault(v, []).append(rva)
t87 = [f for f in taken if f in x87_fn]
t87_clo = [f for f in t87 if f in seen]
print('[D] DIR64 sites pointing at a pdata function start: %d functions (x87 funcs %d, of which in closure %d)' % (
    len(taken), len(t87), len(t87_clo)))
in_text = sum(1 for f in t87 for r in taken[f] if tlo <= r < thi)
print('[D] x87 function pointer sites: in .text %d / outside .text %d' % (
    in_text, sum(len(taken[f]) for f in t87) - in_text))
lea_x87 = [f for f in code_refs if f in x87_fn]
refr = {r for f in lea_x87 for r in code_refs[f]}
print('[E] x87 funcs whose start is taken by code (rip-relative lea): %d funcs, from %d referrer funcs' % (len(lea_x87), len(refr)))
print('[E] referrer funcs inside the export closure: %d (x87 funcs taken by a closure referrer: %d)' % (
    len(refr & seen), sum(1 for f in lea_x87 if any(r in seen for r in code_refs[f]))))
