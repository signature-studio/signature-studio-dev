#!/usr/bin/env python3
"""PY-4770 (#4770): general.saveUndo の未確定点のうち PE から確定した事実を検査する (実機不要)。

  FL_WIN64_DIR=<展開先> python3 analysis/py4770_saveundo_open.py

PE は fl-win64 素材の extracted/block00031_PE.bin (ImageBase 0x400000)。
検査する事実は REPORT_PY124.md §4-2b の表と 1 対 1 に対応する。
全検査が通れば PASS を出し、外れれば AssertionError で止まる。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
MASK_GATE_A = 0x101B9E2   # and rax, [rip+...]  (mask & A)
MASK_GATE_B = 0x101B9E9   # cmp rax, [rip+...]  (== B)
MASK_GATE_JE = 0x101B9F0  # je 0x101bb0c (== B のとき +0x80 への書込みを飛ばす)
CONST_A_VA = 0x101BD54
CONST_B_VA = 0x101BD5C
SKIP_TARGET = 0x101BB0C
ENTRY_REG_ARG = 0x1019EE3  # movzx r8, byte [rip+...] (registry の 2 番目 flags)
REG_FLAG_VA = 0x1019F70
CTOR = 0x1019E30
REG_BUILD = 0x102C9B0
REG_FILL = 0x102CA60
CAT_HASH = 0x102B6C0
CAT_PROBE = 0x102B610
CAT_LOOKUP = 0x102BB20
ARR_RELEASE = 0x418190
ARR_ASSIGN = 0x418210
DELETE_OBJ = 0x40FAA0


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(PE, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def off(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def insns(va, n=0x800):
        return list(md.disasm(data[off(va):off(va) + n], va))

    def at(va):
        return {i.address: i for i in insns(va, 0x1400)}

    def rip_target(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    def qword(va):
        return struct.unpack("<Q", data[off(va):off(va) + 8])[0]

    def byte(va):
        return data[off(va)]

    body = at(0x101B780)

    a = body[MASK_GATE_A]
    assert a.mnemonic == "and" and rip_target(a) == CONST_A_VA, a
    b = body[MASK_GATE_B]
    assert b.mnemonic == "cmp" and rip_target(b) == CONST_B_VA, b
    assert qword(CONST_A_VA) == 0x10000000004, hex(qword(CONST_A_VA))
    assert qword(CONST_B_VA) == 0, hex(qword(CONST_B_VA))
    j = body[MASK_GATE_JE]
    assert j.mnemonic == "je" and int(j.op_str, 16) == SKIP_TARGET, j.op_str
    print(f"mask gate: A={qword(CONST_A_VA):#x} B={qword(CONST_B_VA):#x} (.text 定数) skip->{SKIP_TARGET:#x}")

    ctor = at(CTOR)
    r8 = ctor[ENTRY_REG_ARG]
    assert r8.mnemonic == "movzx" and rip_target(r8) == REG_FLAG_VA, r8
    assert byte(REG_FLAG_VA) == 0x02, hex(byte(REG_FLAG_VA))
    print(f"ctor registry flags: byte[{REG_FLAG_VA:#x}] = {byte(REG_FLAG_VA)} (bit1 のみ)")

    fill = at(REG_FILL)
    assert any(i.mnemonic == "test" and i.op_str == "al, 1" for i in fill.values())
    assert any(i.mnemonic == "test" and i.op_str == "al, 2" for i in fill.values())
    print("registry fill: bit0 / bit1 の 2 経路 (0x102ca60)")

    h = insns(CAT_HASH, 0x40)
    assert any(i.mnemonic == "call" and "[rax + 0x20]" in i.op_str for i in h), "0x102b6c0 vtbl+0x20"
    assert any(i.mnemonic == "and" and i.op_str == "eax, 0x7fffffff" for i in h)
    probe = insns(CAT_PROBE, 0x200)
    assert any(i.mnemonic == "cmp" and i.op_str == "eax, -1" for i in probe), "0x102b610 empty"
    assert any(i.mnemonic == "call" and "[rax + 0x18]" in i.op_str for i in probe), "0x102b610 vtbl+0x18"
    print("category index: 0x102b6c0 (hash, c 非依存) / 0x102b610 (線形探索, vtbl+0x18(value, c))")

    lk = insns(CAT_LOOKUP, 0x80)
    assert any(i.mnemonic == "mov" and i.op_str == "rcx, qword ptr [rdx + rcx*8 + 8]" for i in lk)
    print("category lookup: 0x102bb20 は要素 +8 を返す")

    arr_rel = insns(ARR_RELEASE, 0x80)
    assert any(i.mnemonic == "lock xadd" for i in arr_rel), "0x418190 refcount"
    arr_asg = {i.address: i for i in insns(ARR_ASSIGN, 0x60)}

    def expect(va, mnemonic, op_str):
        ins = arr_asg[va]
        assert ins.mnemonic == mnemonic and ins.op_str == op_str, (hex(va), ins.mnemonic, ins.op_str)

    expect(0x418223, "je", "0x41823b")
    expect(0x418229, "jge", "0x41823b")
    expect(0x418234, "call", "0x418000")
    assert arr_asg[0x418239].mnemonic == "jmp" and arr_asg[0x418239].op_str == "0x418251", "0x418239 jump"
    expect(0x41823E, "call", "0x418260")
    expect(0x418249, "call", "0x418190")
    expect(0x41824E, "mov", "qword ptr [rbx], rsi")
    print("array assign: 共有経路 (0x41823b→0x418260→0x418190→dst=src) と複写経路 (0x418000→0x418239→0x418251)")

    rel = {i.address: i for i in insns(0x1019DD0, 0x60)}
    assert rel[0x1019DD0].mnemonic == "push", "0x1019dd0 head"
    assert rel[0x1019DDA].mnemonic == "mov" and rel[0x1019DDA].op_str == "rax, qword ptr [rbx + 0x20]", "0x1019dd0 arr"
    assert rel[0x1019DE3].mnemonic == "mov" and rel[0x1019DE3].op_str == "rax, qword ptr [rax - 8]", "0x1019dd0 count"
    assert rel[0x1019E03].mnemonic == "call" and rel[0x1019E03].op_str == "0x40faa0", "0x1019dd0 loop call"
    assert rel[0x1019E13].mnemonic == "lea" and rel[0x1019E13].op_str == "rcx, [rbx + 0x20]", "0x1019dd0 release arg"
    assert rel[0x1019E1E].mnemonic == "call" and rel[0x1019E1E].op_str == "0x418190", "0x1019dd0 release call"
    print("0x1019dd0 = [arr-8] 件数分の 0x40faa0 の後に 0x418190")

    dele = insns(DELETE_OBJ, 0x30)
    assert any(i.mnemonic == "call" and "[rbx - 0x20]" in i.op_str for i in dele), "0x40faa0 vtbl-0x20"
    print("0x40faa0 = virtual delete ([vtbl-0x20](obj, 1))")

    print("PASS: py4770 saveUndo open facts")


if __name__ == "__main__":
    main()
