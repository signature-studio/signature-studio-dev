#!/usr/bin/env python3
"""G1 0xbd0ba0 の呼出し前段を追う (#5932)。entry 0x1376820 の全命令を記録し、
import スタブの呼出しと、初期化テーブルの handler 呼出し件数を出す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/g1_trace_5932.py [出力 txt]

出力 txt は全命令の列 (約 2 万行)。既定は work/5932/full_trace.txt (gitignore)。
"""
import os
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from unicorn import (Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED, UC_HOOK_MEM_FETCH_UNMAPPED)
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RBP, UC_X86_REG_RCX

PAGE = 0x1000
PE_PATH = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
OUT = sys.argv[1] if len(sys.argv) > 1 else "work/5932/full_trace.txt"
STUB = 0x10000000
STUB_SIZE = 0x100000
STACK_TOP = 0x30100000
STACK_SIZE = 0x400000
TEB = 0x7FF00000
HEAP = 0x50000000
HEAP_SIZE = 0x10000000
ENTRY_VA = 0x1376820
MAX_INS = 2000000


def align(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


def main():
    pe = pefile.PE(data=open(PE_PATH, "rb").read())
    base = pe.OPTIONAL_HEADER.ImageBase
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, align(pe.OPTIONAL_HEADER.SizeOfImage), UC_PROT_ALL)
    for s in pe.sections:
        data = s.get_data()[: s.SizeOfRawData]
        if data:
            uc.mem_write(base + s.VirtualAddress, data)
    uc.mem_map(STUB, STUB_SIZE, UC_PROT_ALL)
    uc.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE, UC_PROT_ALL)
    uc.mem_map(TEB, PAGE, UC_PROT_ALL)
    uc.mem_map(HEAP, HEAP_SIZE, UC_PROT_ALL)

    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    names = {}
    n = 0
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in e.imports:
            stub = STUB + n * 16
            uc.mem_write(imp.address, struct.pack("<Q", stub))
            fn = imp.name.decode(errors="replace") if imp.name else "ord%s" % imp.ordinal
            names[stub] = "%s!%s" % (e.dll.decode(errors="replace"), fn)
            n += 1

    calls = []

    def stub_hook(u, addr, size_, _):
        if addr in names:
            rsp = u.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack("<Q", bytes(u.mem_read(rsp, 8)))[0]
            calls.append((names[addr], hex(ret)))
            u.reg_write(UC_X86_REG_RAX, 0)
            u.reg_write(UC_X86_REG_RSP, rsp + 8)
            u.reg_write(UC_X86_REG_RIP, ret)

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    lines = []
    cnt = [0]

    def code_hook(u, addr, size_, _):
        cnt[0] += 1
        if STUB <= addr < STUB + STUB_SIZE:
            return
        ins = next(md.disasm(bytes(u.mem_read(addr, 16)), addr), None)
        lines.append("%#x: %s %s" % (addr, ins.mnemonic, ins.op_str) if ins else "%#x: ?" % addr)
        if cnt[0] >= MAX_INS:
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, stub_hook, begin=STUB, end=STUB + STUB_SIZE - 1)
    uc.hook_add(UC_HOOK_CODE, code_hook)
    reason = {"v": "正常終了"}

    def unmapped(u, access, addr, size_, value, _):
        reason["v"] = "未マップ参照 access=%d addr=%#x" % (access, addr)
        return False

    uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED, unmapped)
    uc.reg_write(UC_X86_REG_RSP, STACK_TOP - 0x100)
    uc.reg_write(UC_X86_REG_RBP, STACK_TOP - 0x100)
    ret_stub = STUB + STUB_SIZE - 16
    uc.mem_write(STACK_TOP - 0x100, struct.pack("<Q", ret_stub))
    try:
        uc.emu_start(ENTRY_VA, ret_stub)
    except Exception as ex:  # unicorn の UcError を含む
        reason["v"] = "例外: %s" % ex

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    handler_calls = sum(1 for l in lines if l.endswith("call qword ptr [rbp + 0x38]"))
    print("ins=%d reason=%s rip=%#x" % (cnt[0], reason["v"], uc.reg_read(UC_X86_REG_RIP)))
    print("import calls=%d" % len(calls))
    for name, ret in calls:
        print("  %s ret=%s" % (name, ret))
    print("handler calls (call [rbp+0x38]) lines=%d" % handler_calls)
    print("0x11be0a0 executed=%s" % any(l.startswith("0x11be0a0:") for l in lines))
    print("trace -> %s" % OUT)


if __name__ == "__main__":
    main()
