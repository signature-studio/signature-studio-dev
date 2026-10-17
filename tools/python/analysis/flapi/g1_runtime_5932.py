#!/usr/bin/env python3
"""G1 0xbd0ba0 (RVA 0x7d0ba0) の実行時値を、初期化時点と 0x11c8950 呼出し時点で採取する (#5932)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/g1_runtime_5932.py [最大命令数] [秒上限]

ハーネスは pe_emu_entry_5458.py と同じ (import は rax=0 で戻すスタブ)。
記録: 起点 (entry) での G1 の 8 バイト、0x11c8950 に最初に入った時点の G1、
      0x11c8950 への到達回数、終了理由、最後の RIP。
"""
import os
import struct
import sys
import time

import pefile
from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED, UC_HOOK_MEM_FETCH_UNMAPPED)
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RBP,
                               UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9)

PAGE = 0x1000
PE_PATH = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
IMAGE = 0x400000
STUB = 0x10000000
STUB_SIZE = 0x100000
STACK_TOP = 0x30100000
STACK_SIZE = 0x400000
TEB = 0x7FF00000
HEAP = 0x50000000
HEAP_SIZE = 0x10000000
ENTRY_VA = 0x1376820
G1_VA = 0xBD0BA0
CALLEE_VA = 0x11C8950
MAX_INS = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000_000
MAX_SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0


def align(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


def main():
    raw = open(PE_PATH, "rb").read()
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = align(pe.OPTIONAL_HEADER.SizeOfImage)
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, size, UC_PROT_ALL)
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
            names[stub] = "%s!%s" % (e.dll.decode(errors="replace"), (imp.name or b"?").decode(errors="replace"))
            n += 1

    def stub_hook(u, addr, size_, _):
        if addr in names:
            rsp = u.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack("<Q", bytes(u.mem_read(rsp, 8)))[0]
            u.reg_write(UC_X86_REG_RAX, 0)
            u.reg_write(UC_X86_REG_RSP, rsp + 8)
            u.reg_write(UC_X86_REG_RIP, ret)

    def g1():
        return struct.unpack("<Q", bytes(uc.mem_read(G1_VA, 8)))[0]

    stats = {"ins": 0, "callee": 0, "last": 0}
    snap = {}
    t0 = time.time()

    def code_hook(u, addr, size_, _):
        stats["ins"] += 1
        stats["last"] = addr
        if "init" not in snap:
            snap["init"] = g1()
        if addr == CALLEE_VA:
            stats["callee"] += 1
            if "callee" not in snap:
                snap["callee"] = g1()
        if stats["ins"] >= MAX_INS or time.time() - t0 > MAX_SEC:
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, stub_hook, begin=STUB, end=STUB + STUB_SIZE - 1)
    uc.hook_add(UC_HOOK_CODE, code_hook)
    reason = {"v": "正常終了"}

    def unmapped(u, access, addr, size_, value, _):
        reason["v"] = "未マップ参照 access=%d addr=%#x" % (access, addr)
        return False

    uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED,
                unmapped)

    uc.reg_write(UC_X86_REG_RSP, STACK_TOP - 0x100)
    uc.reg_write(UC_X86_REG_RBP, STACK_TOP - 0x100)
    for r in (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9):
        uc.reg_write(r, 0)
    ret_stub = STUB + STUB_SIZE - 16
    uc.mem_write(STACK_TOP - 0x100, struct.pack("<Q", ret_stub))
    try:
        uc.emu_start(ENTRY_VA, ret_stub)
    except UcError as ex:
        reason["v"] = "UcError: %s" % ex
    el = time.time() - t0
    print("base=%#x G1=%#x (static value at load)" % (base, G1_VA))
    print("ins=%d sec=%.2f" % (stats["ins"], el))
    print("reason=%s rip=%#x last_code=%#x" % (reason["v"], uc.reg_read(UC_X86_REG_RIP), stats["last"]))
    print("G1 at first instruction (init)=%#x" % snap.get("init", 0))
    print("callee %#x hits=%d" % (CALLEE_VA, stats["callee"]))
    if "callee" in snap:
        print("G1 at first callee entry=%#x" % snap["callee"])
    else:
        print("G1 at callee entry: 未到達")


if __name__ == "__main__":
    main()
