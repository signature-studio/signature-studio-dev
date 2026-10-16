#!/usr/bin/env python3
# usage: ks_vtable_reader.py <SlateCore.core_64> <table_va_hex> <vtable_va_hex> [--ctor-va hex ...]
# 関数ポインタ表 (table = vtable + slot*8) を読む命令を、rip 相対以外の形も含めて列挙する。
#   1) 表・vtable の絶対値 (即値 / disp / rip 相対 ea)、RVA 形 (dword) の参照
#   2) vtable を書く lea/mov (rip 相対) とその所属関数 (pdata)
#   3) [reg+disp] で disp == slot*8 の読み (間接 call/jmp と mov) の総数と、所属関数が vtable 書き関数か
import sys, struct, argparse, pefile, capstone

ap = argparse.ArgumentParser()
ap.add_argument("pe")
ap.add_argument("table", type=lambda s: int(s, 16))
ap.add_argument("vtable", type=lambda s: int(s, 16))
ap.add_argument("--ctor-va", type=lambda s: int(s, 16), action="append", default=[])
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
M64 = 0xFFFFFFFFFFFFFFFF
slot_disp = a.table - a.vtable
X86 = capstone.x86
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
funcs = sorted((base + d.struct.BeginAddress, base + d.struct.EndAddress) for d in pe.DIRECTORY_ENTRY_EXCEPTION)
starts = [f[0] for f in funcs]
import bisect


def owner(x):
    i = bisect.bisect_right(starts, x) - 1
    if i >= 0 and funcs[i][0] <= x < funcs[i][1]:
        return funcs[i][0]
    return None


abs_hits, rva_hits, vt_writes, slot_reads = [], [], [], []
for s in pe.sections:
    if not (s.Characteristics & 0x20000000):
        continue
    data = s.get_data()
    va0 = base + s.VirtualAddress
    off = 0
    while off < len(data):
        ins = next(iter(md.disasm(data[off:off + 16], va0 + off)), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        for op in ins.operands:
            if op.type == X86.X86_OP_IMM:
                v = op.imm & M64
                if v in (a.table, a.vtable):
                    abs_hits.append(ins)
            elif op.type == X86.X86_OP_MEM:
                m = op.mem
                if m.base == X86.X86_REG_RIP:
                    ea = (ins.address + ins.size + m.disp) & M64
                    if ea in (a.table, a.vtable):
                        if ins.mnemonic == "lea":
                            vt_writes.append(ins)
                        else:
                            abs_hits.append(ins)
                elif m.base == 0 and m.index == 0:
                    if (m.disp & M64) in (a.table, a.vtable):
                        abs_hits.append(ins)
                if m.base != X86.X86_REG_RIP and m.index == 0 and (m.disp & M64) == slot_disp:
                    slot_reads.append(ins)
        if len(ins.operands) == 1 and ins.operands[0].type == X86.X86_OP_IMM:
            pass

rva = struct.pack("<I", (a.table - base) & 0xFFFFFFFF)
print(f"table {a.table:#x} vtable {a.vtable:#x} slot_disp {slot_disp:#x}")
print("abs/imm/disp hits:", len(abs_hits))
for ins in abs_hits:
    print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
print("rip-relative lea writes to vtable/table:", len(vt_writes))
for ins in vt_writes:
    f = owner(ins.address)
    print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}  func={f and hex(f)}")
print("[reg+%#x] reads (any base register):" % slot_disp, len(slot_reads))
calls = [i for i in slot_reads if i.mnemonic in ("call", "jmp")]
print("  as indirect call/jmp:", len(calls))
ctors = set(a.ctor_va)
for ins in vt_writes:
    f = owner(ins.address)
    if f:
        ctors.add(f)
inside = [i for i in slot_reads if owner(i.address) in ctors]
print("  inside vtable-writer functions:", len(inside))
for ins in inside:
    print(f"    {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
print("  distinct functions containing a slot read:", len({owner(i.address) for i in slot_reads}))
