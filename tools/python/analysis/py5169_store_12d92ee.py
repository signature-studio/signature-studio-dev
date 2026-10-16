#!/usr/bin/env python3
"""PY-4878 (#5169): 0x12d92ee `mov dword ptr [rip+disp], eax` の書込み先と値の源を検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/py5169_store_12d92ee.py

前提 (前 run の静的解析の結論): 書込み先は VA 0x193fce8 (slot 0x15e4018 ではない)、
値は dword [*(0x15e3730)] (0x15e3730 は .data のポインタセル、指す先は .bss)。
差分が出たら exit 1。展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
STORE = 0x12D92EE
EXPECT_DST = 0x193FCE8
SRC_CELL = 0x15E3730


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = pe.sections

    def to_off(va):
        rva = va - base
        for s in secs:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        sys.exit("VA が section 外: %#x" % va)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    o = to_off(STORE)
    ins = next(md.disasm(raw[o:o + 16], STORE))
    ok = True
    dst = ins.address + ins.size + int(ins.op_str.split("[rip + ")[1].split("]")[0], 16) \
        if "[rip + " in ins.op_str else None
    print("store: %#x %s %s -> dst %s" % (ins.address, ins.mnemonic, ins.op_str, hex(dst) if dst else "?"))
    if ins.mnemonic != "mov" or dst != EXPECT_DST or not ins.op_str.endswith(", eax"):
        ok = False
    # 直前の 2 命令: rax = [SRC_CELL]; eax = [rax]
    prev = list(md.disasm(raw[to_off(STORE - 0x20):to_off(STORE)], STORE - 0x20))[-3:]
    for p in prev:
        print("  %#x %s %s" % (p.address, p.mnemonic, p.op_str))
    load_cell = [p for p in prev if p.mnemonic == "mov" and p.op_str.startswith("rax, qword ptr [rip + ")]
    if not load_cell:
        ok = False
    else:
        p = load_cell[-1]
        cell = p.address + p.size + int(p.op_str.split("[rip + ")[1].split("]")[0], 16)
        print("  rax source cell: %#x" % cell)
        if cell != SRC_CELL:
            ok = False
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
