#!/usr/bin/env python3
"""PY-5414 (#6015) の D の型の手がかり: dl=1 経路の factory `0x40f960` を PE から読む。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py69_d_factory_probe.py

- (1) 0x40f960: rcx (this) から 0x409410 で確保し、0x40fb40 で初期化して、確保したブロックを返す。
- (2) 0x40fb40: `mov [rsi],rdi` (先頭 qword に this を格納) と `mov rax,rsi` (戻り値) を確認する。
- (3) 0x40fb40 のリスト走査は `[rsi + r9]` に書く。r9 はレコードの dword (+0x18) なので、
  書込み先オフセットは静的に決まらない (出力に記録するだけ)。
- (4) 0x409410: 確保の入口。IAT 間接呼出し `call [rip+..]` の戻りを返す。
- (5) データ: `[0x855878]`=0x855940、仮想呼出し先 qword `0x855910`=0x40f960、dword `0x8558c0`=728 を読む。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fo(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + rva - s.VirtualAddress
    raise SystemExit(f"VA {va:#x} が section 外")


def qword(va):
    return struct.unpack_from("<Q", RAW, fo(va))[0]


def dword(va):
    return struct.unpack_from("<I", RAW, fo(va))[0]


def fn(start, end):
    return list(MD.disasm(RAW[fo(start):fo(start) + (end - start)], start))


def show(name, start, end):
    print(f"--- {name} {start:#x}-{end:#x}")
    for i in fn(start, end):
        print(f"  {i.address:x}: {i.mnemonic} {i.op_str}")


def has(insns, mnem, op):
    return any(i.mnemonic == mnem and i.op_str == op for i in insns)


def main():
    f960 = fn(0x40F960, 0x40F982)
    f40b = fn(0x40FB40, 0x40FBFF)
    f410 = fn(0x409410, 0x409440)
    show("(1) factory", 0x40F960, 0x40F982)
    print("    calls:", [(hex(i.address), i.op_str) for i in f960 if i.mnemonic == "call"])
    assert has(f960, "call", "0x409410") and has(f960, "call", "0x40fb40")
    show("(2) init 0x40fb40 (先頭 40 命令)", 0x40FB40, 0x40FB40 + 0x60)
    assert has(f40b, "mov", "qword ptr [rsi], rdi"), "[rsi]=this が無い"
    assert has(f40b, "mov", "rax, rsi"), "戻り値 rsi が無い"
    print("    [rsi]=this: 有り / 戻り値 rsi を rax へ: 有り")
    print("    [rsi+r9] の書込み (データ駆動オフセット):",
          sum(1 for i in f40b if i.mnemonic == "mov" and "[rsi + r9]" in i.op_str))
    show("(4) 確保 0x409410", 0x409410, 0x409436)
    assert any(i.mnemonic == "call" and "qword ptr [rip" in i.op_str for i in f410)
    print("(5) data:")
    v878 = qword(0x855878)
    v910 = qword(0x855940 - 0x30)
    v8c0 = dword(0x855940 - 0x80)
    print(f"    [0x855878] = {v878:#x}")
    print(f"    [0x855940-0x30] (0x855910) = {v910:#x}")
    print(f"    dword [0x855940-0x80] (0x8558c0) = {v8c0}")
    assert v878 == 0x855940, "[0x855878] が 0x855940 でない"
    assert v910 == 0x40F960, "仮想呼出し先が 0x40f960 でない"
    assert v8c0 == 728, "確保サイズが 728 でない"
    print("ok")


if __name__ == "__main__":
    main()
