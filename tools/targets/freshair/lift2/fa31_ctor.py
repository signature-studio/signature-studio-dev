#!/usr/bin/env python3
"""fa31_ctor.py <SlateCore.core_64> — FA-31 (#5254): ModulationKnobsPopup (vtable 0x18110a420, slot 5 = d8c0b0) の
構築関数と、その P (this) の +0xb88・+0xb98・+0xba8 への書込みを静的に列挙する (診断のみ・判定は出さない)。
直接の mov (rip 相対 vtable lea・[reg+disp] への書込み) だけを見る。間接書込み・memcpy・呼出先での書込みは見ない。"""
import re, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

VT = 0x18110a420
CTOR_CALLERS_OF = None
pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
RIP = re.compile(r"rip \+ 0x([0-9a-f]+)")
STORE = re.compile(r"^(qword|dword|byte) ptr \[(r[a-z0-9]+) \+ 0x(b88|b98|ba8)\], ")

funcs = []
for rf in pe.DIRECTORY_ENTRY_EXCEPTION:
    b = base + rf.struct.BeginAddress
    e = base + rf.struct.EndAddress
    funcs.append((b, e, rf.struct.BeginAddress, e - b))

vt_writers = []
for b, e, rva, sz in funcs:
    ins = list(md.disasm(pe.get_data(rva, sz), b))
    for i in ins:
        m = RIP.search(i.op_str)
        if m and i.address + i.size + int(m.group(1), 16) == VT:
            vt_writers.append((b, ins))
            break

for b, ins in vt_writers:
    print("VT 0x%x を書く関数: %x" % (VT, b))
    for i in ins:
        if i.mnemonic == "mov" and STORE.search(i.op_str):
            print("   %x mov %s" % (i.address, i.op_str))

ctor = vt_writers[0][0] if vt_writers else None
if ctor is not None:
    for b, e, rva, sz in funcs:
        ins = list(md.disasm(pe.get_data(rva, sz), b))
        for k, i in enumerate(ins):
            if i.mnemonic == "call" and i.op_str.startswith("0x") and int(i.op_str, 16) == ctor:
                print("ctor 呼出元: %x (所属 %x)" % (i.address, b))

n = 0
for b, e, rva, sz in funcs:
    for i in md.disasm(pe.get_data(rva, sz), b):
        if i.mnemonic == "mov" and re.search(r"^(qword|dword|byte) ptr \[r[a-z0-9]+ \+ 0x(b98|ba8)\], ", i.op_str):
            if "rsp" in i.op_str or "rbp" in i.op_str:
                continue
            n += 1
print("スタック以外の基底への +0xb98/+0xba8 書込み (全 .text): %d 件" % n)
