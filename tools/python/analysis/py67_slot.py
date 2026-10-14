#!/usr/bin/env python3
"""PY-67 (#2159): .data の slot を経由する間接参照を追う (実機不要)。

  python3 analysis/py67_slot.py <PE.bin> <slot VA hex> <global VA hex> [window]

前提: slot の中身が global の絶対値 (&global) である。コードは `mov reg,[rip+slot]` で
&global (depth 1) を得て、続けて `mov reg,[reg]` で *global (depth 2) を得る。
- depth 1 の基底への store: global 自体 (g) への書込み。
- depth 2 の基底への store: g が指すオブジェクト P への書込み。

1. .text を 1 回線形走査する。
2. slot 由来のレジスタを追跡する (mov 複写・基底 0 の mov 逆参照で depth を増やす。
   それ以外の書込みで追跡を止める)。call で caller-saved を破棄し、ret/jmp で全破棄。
3. depth 別の mov store、slot/global への RIP 相対参照、global の即値を出す。
4. slot 由来 (depth 1/2) を引数に取る direct call の先頭 40 命令で、その引数レジスタへの書込みを出す。
採用前に py58_context.py で命令境界を確認すること。
"""
import re
import struct
import sys

import capstone
import pefile

path = sys.argv[1]
slot = int(sys.argv[2], 0)
glob = int(sys.argv[3], 0)
window = int(sys.argv[4], 0) if len(sys.argv) > 4 else 60

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff = text.PointerToRawData
tsize = text.SizeOfRawData
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
tdata = data[toff:toff + tsize]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X = capstone.x86
WRITE = capstone.CS_AC_WRITE
ARG_REGS = ("rcx", "rdx", "r8", "r9")
CALLER_SAVED = ("rax", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11")
NO_WRITE = {"cmp", "test", "push", "bt", "ucomiss", "ucomisd", "comiss", "comisd", "jmp", "call"}


def canon(name):
    if not name:
        return ""
    m = re.fullmatch(r"r(\d+)[dwbl]?", name)
    if m:
        return f"r{m.group(1)}"
    if name in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"):
        return name
    m = re.fullmatch(r"e(ax|bx|cx|dx|si|di|bp|sp)|(ax|bx|cx|dx|si|di|bp|sp)", name)
    if m:
        return "r" + (m.group(1) or m.group(2))
    m = re.fullmatch(r"([abcd])[lh]", name)
    if m:
        return "r" + m.group(1) + "x"
    if name in ("sil", "dil", "bpl", "spl"):
        return "r" + name[:2]
    return name


def reg_of(md_, op):
    return canon(md_.reg_name(op.reg))


tracked = {}
stores = []
calls = []
slot_loads = 0
slot_refs = []
glob_refs = []
imms = []

off = 0
idx = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    idx += 1
    ops = ins.operands
    mn = ins.mnemonic

    for r in [r for r, v in tracked.items() if idx - v[0] > window]:
        del tracked[r]
    if mn == "ret" or mn.startswith("ret") or mn in ("jmp", "int3"):
        tracked.clear()
    if mn == "call":
        callee = ops[0].imm if ops and ops[0].type == X.X86_OP_IMM else None
        for r in ARG_REGS:
            if r in tracked:
                calls.append((ins.address, r, tracked[r][2], callee, tracked[r][1]))

    for op in ops:
        if op.type == X.X86_OP_MEM and op.mem.base != 0:
            base = canon(md.reg_name(op.mem.base))
            if base in tracked and op.access & WRITE and mn == "mov" and ops[0] is op:
                stores.append((ins.address, ins.op_str, tracked[base][2], tracked[base][1], idx - tracked[base][0]))
        if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
            tgt = ins.address + ins.size + op.mem.disp
            kind = "lea" if mn == "lea" else ("STORE" if op.access & WRITE else "load")
            if tgt == slot:
                slot_refs.append(f"{ins.address:#x}: {mn} {ins.op_str}  -> {tgt:#x}  [{kind}]")
            if tgt == glob:
                glob_refs.append(f"{ins.address:#x}: {mn} {ins.op_str}  -> {tgt:#x}  [{kind}]")
        if op.type == X.X86_OP_IMM and op.imm in (glob, slot):
            imms.append(f"{ins.address:#x}: {mn} {ins.op_str}")

    if mn == "call":
        for r in CALLER_SAVED:
            tracked.pop(r, None)
        continue

    dst = reg_of(md, ops[0]) if ops and ops[0].type == X.X86_OP_REG else None
    if dst is not None and mn in NO_WRITE:
        dst = None
    if mn == "mov" and len(ops) == 2 and dst is not None:
        src = ops[1]
        if src.type == X.X86_OP_MEM and src.mem.base == X.X86_REG_RIP and ins.address + ins.size + src.mem.disp == slot:
            tracked[dst] = (idx, ins.address, 1)
            slot_loads += 1
            continue
        if src.type == X.X86_OP_MEM and src.mem.base != 0 and src.mem.index == 0 and src.mem.disp == 0:
            sb = canon(md.reg_name(src.mem.base))
            if sb in tracked and tracked[sb][2] < 2:
                _, origin, depth = tracked[sb]
                tracked[dst] = (idx, origin, depth + 1)
                continue
        if src.type == X.X86_OP_REG and canon(md.reg_name(src.reg)) in tracked:
            tracked[dst] = tracked[canon(md.reg_name(src.reg))]
            continue
    if dst is not None:
        tracked.pop(dst, None)

for t, val in (("slot", slot), ("global", glob)):
    for width, fmt in ((8, "<Q"), (4, "<I")):
        needle = struct.pack(fmt, val)
        hits = []
        pos = data.find(needle)
        while pos != -1:
            hits.append(pos)
            pos = data.find(needle, pos + 1)
        print(f"# [{t} {val:#x}] absolute {width}-byte value: {len(hits)} hit(s)")
        for h in hits[:20]:
            sec = next((s.Name.rstrip(b"\0").decode() for s in pe.sections
                        if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData), "?")
            print(f"#   file offset {h:#x} section={sec}")

print(f"# slot loads (mov reg,[rip+slot]): {slot_loads}, window {window}, call/ret cut")
print(f"# RIP refs to slot {slot:#x}: {len(slot_refs)}")
print(f"# RIP refs to global {glob:#x}: {len(glob_refs)}")
for line in glob_refs:
    if "[load]" not in line:
        print(f"  {line}")
print(f"# immediates equal to slot/global: {len(imms)}")
for line in imms:
    print(f"  {line}")
d1 = [s for s in stores if s[2] == 1]
d2 = [s for s in stores if s[2] == 2]
print(f"# mov-stores via &global (depth 1): {len(d1)}")
for a, op, d, origin, dist in d1:
    print(f"  {a:#x}: mov {op}  [slot-load {origin:#x}, +{dist} ins]")
print(f"# mov-stores via *global (depth 2, object P): {len(d2)}")
offs = {}
for a, op, d, origin, dist in d2:
    offs.setdefault(op.split("[", 1)[1].split("]", 1)[0] if "[" in op else op, []).append(a)
for k in sorted(offs):
    print(f"  [{k}] x{len(offs[k])} e.g. {offs[k][0]:#x}")
print(f"# direct calls with a slot-derived arg reg (rcx/rdx/r8/r9): {len(calls)}")
for site, reg, depth, callee, origin in calls:
    tag = "&global" if depth == 1 else "*global"
    print(f"  call {site:#x} {reg}={tag} from slot-load {origin:#x} -> {('%#x' % callee) if callee is not None else 'indirect'}")


def callee_writes(va, reg, depth=40):
    lo = va - tbase
    if not (0 <= lo < tsize):
        return []
    out = []
    for c in md.disasm(tdata[lo:lo + 15 * depth], va, depth):
        for op in c.operands:
            if op.type == X.X86_OP_MEM and op.mem.base != 0 and canon(md.reg_name(op.mem.base)) == reg and op.access & WRITE:
                out.append(f"{c.address:#x}: {c.mnemonic} {c.op_str}")
        if c.mnemonic.startswith("ret"):
            break
        if any(canon(md.reg_name(w)) == reg for w in c.regs_write):
            break
    return out


for callee in sorted({c[3] for c in calls if c[3] is not None}):
    regs = {c[1] for c in calls if c[3] == callee}
    for reg in sorted(regs):
        hits = callee_writes(callee, reg)
        print(f"# callee {callee:#x} via {reg}: writes in first 40 ins through {reg}: {len(hits)}")
        for h in hits:
            print(f"    {h}")
