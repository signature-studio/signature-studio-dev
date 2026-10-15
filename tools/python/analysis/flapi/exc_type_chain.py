#!/usr/bin/env python3
"""PY-106 (#2909): RANGE (-4) の例外型の参照チェーンを PE の静的な値で検算する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/exc_type_chain.py

検算項目 (1 つでも外れたら rc 1):
  (1) .data の chain 先 0x15e1140 の値 = 束縛 slot 0x16b8488
  (2) sink 0xd82daf の load 3 段 (rcx = [[[0x15e1140]]])
  (3) 束縛 slot 0x16b8488 の名前 = PyExc_RuntimeError (束縛関数 0xc395a0 内の lea → resolver → store)
  (4) sink の呼出し先 [rbx] (rbx = [0x15e49b8]) の slot 0x16b8408 の名前 = PyErr_SetString
  (5) -4 の分岐 (0xd82c97 → 0xd82d3c) の文言 = "Index out of range" で、共通 sink 0xd82da6 へ jmp する
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHAIN_HEAD, SLOT_EXC, SLOT_SETSTR, RBX_CELL = 0x15e1140, 0x16b8488, 0x16b8408, 0x15e49b8
SINK_TOP, SINK_LOAD, RANGE_BRANCH, COMMON_HEAD = 0xd82daf, 0xd82daf, 0xd82d3c, 0xd82da6
BIND_LO, BIND_HI = 0xc395a0, 0xc3a200

pe = pefile.PE(PE, fast_load=True)
RAW = open(PE, "rb").read()
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True
RIP = capstone.x86.X86_REG_RIP
MEM = capstone.x86.X86_OP_MEM
fails = []


def off(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise ValueError(hex(va))


def qword(va):
    return int.from_bytes(RAW[off(va):off(va) + 8], "little")


def cstr(va):
    return RAW[off(va):off(va) + 80].split(b"\0")[0].decode("latin1")


def wstr(va):
    return RAW[off(va):off(va) + 160].decode("utf-16le", "replace").split("\0")[0]


def disasm(va, size):
    return list(MD.disasm(RAW[off(va):off(va) + size], va))


def ripmem(ins):
    for op in ins.operands:
        if op.type == MEM and op.mem.base == RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def check(name, ok, detail):
    print(f"{'OK ' if ok else 'NG '}{name}: {detail}")
    if not ok:
        fails.append(name)


def bind_name(slot):
    last = None
    for ins in disasm(BIND_LO, BIND_HI - BIND_LO):
        if ins.mnemonic == "lea" and ins.op_str.startswith("rdx,"):
            last = ripmem(ins)
        if ins.mnemonic == "mov" and ins.op_str.startswith("qword ptr [rip") and ins.op_str.endswith(", rax") and ripmem(ins) == slot:
            return wstr(last) if last else None
    return None


def main():
    v = qword(CHAIN_HEAD)
    check("(1) .data chain", v == SLOT_EXC, f"[0x{CHAIN_HEAD:x}] = 0x{v:x} (slot 0x{SLOT_EXC:x})")

    sink = disasm(SINK_TOP, 16)
    first = sink[0]
    three = first.mnemonic == "mov" and ripmem(first) == CHAIN_HEAD and sink[1].op_str == "rcx, qword ptr [rcx]" and sink[2].op_str == "rcx, qword ptr [rcx]"
    check("(2) sink load x3", three, f"{first.address:#x} {first.mnemonic} {first.op_str} / {sink[1].op_str} / {sink[2].op_str}")

    name = bind_name(SLOT_EXC)
    check("(3) slot 0x16b8488 name", name == "PyExc_RuntimeError", f"bind name = {name!r}")

    call = [i for i in disasm(SINK_TOP, 40) if i.mnemonic == "call" and i.op_str == "qword ptr [rbx]"]
    rbx = qword(RBX_CELL)
    setstr = bind_name(SLOT_SETSTR)
    check("(4) call [rbx] = PyErr_SetString", bool(call) and rbx == SLOT_SETSTR and setstr == "PyErr_SetString",
          f"rbx=[0x{RBX_CELL:x}]=0x{rbx:x}, slot name = {setstr!r}, call sites = {len(call)}")

    br = disasm(RANGE_BRANCH, 16)
    msg = None
    for ins in br:
        if ins.mnemonic == "lea" and ins.op_str.startswith("rdx,"):
            msg = cstr(ripmem(ins))
            break
    jmp = [i for i in disasm(RANGE_BRANCH, 40) if i.mnemonic == "jmp"]
    check("(5) -4 branch", msg == "Index out of range" and jmp and jmp[0].operands[0].imm == COMMON_HEAD,
          f"msg = {msg!r}, jmp = {hex(jmp[0].operands[0].imm) if jmp else None}")

    print("RESULT", "PASS" if not fails else "FAIL", f"fails={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
