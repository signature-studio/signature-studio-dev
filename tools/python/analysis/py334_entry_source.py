#!/usr/bin/env python3
"""PY-334 (#4494): 0x1046a30 の入口レジスタ葉 c_in (ecx)・d_in (edx)・r8_in (r8d) の呼出し側の出どころを PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py334_entry_source.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
各 assert は呼出し鎖の 1 命令に対応する (失敗すると非 0 で終わる)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def at(va):
    return next(md.disasm(raw[fo_of(va):fo_of(va) + 16], va))


FAILED = []


def check(label, va, mnemonic, op_str):
    i = at(va)
    ok = i.mnemonic == mnemonic and i.op_str == op_str
    print(("ok   " if ok else "FAIL ") + f"{va:#x}: {label}")
    if not ok:
        FAILED.append(label)


check("PyArg 'Iii': eventId の出力先 [rbp+0x7c] (arg3)", 0xD69F3C, "lea", "r8, [rbp + 0x7c]")
check("PyArg 'Iii': value の出力先 [rbp+0x78] (arg4)", 0xD69F40, "lea", "r9, [rbp + 0x78]")
check("PyArg 'Iii': flags の出力先 [rbp+0x74] (arg5・スタック)", 0xD69F44, "lea", "rax, [rbp + 0x74]")
check("0xd69f00: eventId [rbp+0x7c] → wrapper の r8d", 0xD69F65, "mov", "r8d, dword ptr [rbp + 0x7c]")
check("0xd69f00: value [rbp+0x78] → wrapper の r9d", 0xD69F69, "mov", "r9d, dword ptr [rbp + 0x78]")
check("0xd69f00: flags [rbp+0x74] → wrapper の [rsp+0x20]", 0xD69F6D, "mov", "eax, dword ptr [rbp + 0x74]")
check("0xd69f00: wrapper 0xd84740 を呼ぶ", 0xD69F74, "call", "0xd84740")
check("wrapper 0xd84740: r8d = eventId (mov r8d, r8d)", 0xD84755, "mov", "r8d, r8d")
check("wrapper: eventId → [rsp+0x20] (dispatch の arg5)", 0xD84758, "mov", "qword ptr [rsp + 0x20], r8")
check("wrapper: value (r9) → [rsp+0x28] (arg6)", 0xD84760, "mov", "qword ptr [rsp + 0x28], r9")
check("dispatch: eventId [rbp+0x80] → job+0x18", 0xD84429, "mov", "rax, qword ptr [rbp + 0x80]")
check("dispatch: job+0x18 へ格納", 0xD84430, "mov", "qword ptr [rbx + 0x18], rax")
check("dispatch: value [rbp+0x88] → job+0x20", 0xD84434, "mov", "rax, qword ptr [rbp + 0x88]")
check("dispatch: job+0x20 へ格納", 0xD8443B, "mov", "qword ptr [rbx + 0x20], rax")
check("dispatch: flags [rbp+0x90] → job+0x28", 0xD8443F, "mov", "rax, qword ptr [rbp + 0x90]")
check("dispatch: job+0x28 へ格納", 0xD84446, "mov", "qword ptr [rbx + 0x28], rax")
check("callback 0xd846e0: ecx = job+0x18 (eventId)", 0xD84716, "mov", "ecx, dword ptr [rbx + 0x18]")
check("callback: edx = job+0x20 (value)", 0xD84719, "mov", "edx, dword ptr [rbx + 0x20]")
check("callback: r8d = job+0x28 (flags)", 0xD8471C, "mov", "r8d, dword ptr [rbx + 0x28]")
check("callback: 0x1046a30 を呼ぶ", 0xD84720, "call", "0x1046a30")
check("0x1046a30: ecx → [rbp+0x5b0] (c_in)", 0x1046D65, "mov", "dword ptr [rbp + 0x5b0], ecx")
check("0x1046a30: edx → [rbp+0x5b8] (d_in)", 0x1046D6B, "mov", "dword ptr [rbp + 0x5b8], edx")

print("")
print("対応: c_in (ecx) = eventId (job+0x18)・d_in (edx) = value (job+0x20)・r8_in (r8d) = flags (job+0x28)")
print("出どころ: Python 側の PyArg 'Iii' (0xd69f00 が eventId・value・flags を読んで 0xd84740 に渡す。REPORT_PY126.md)。")

if FAILED:
    print(f"FAIL {len(FAILED)} 件")
    sys.exit(1)
print("summary: 入口レジスタ葉の呼出し鎖は PE と一致 (assert 全件 ok)")
