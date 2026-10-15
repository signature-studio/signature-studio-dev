#!/usr/bin/env python3
"""FLEngine PE の import thunk (`jmp qword ptr [rip+disp]`) の VA から、呼ばれる API 名 (DLL!名前) を引く
(PY-110 の解析補助。call 先が thunk か IAT 本体かを分けて表示する)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_iat_name.py <VA(16進)>[,<VA(16進)>...]

thunk の先 = 次命令アドレス + disp (絶対 VA)。その IAT スロット VA を import 表と照合する。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    targets = [int(x, 16) for x in sys.argv[1].split(",")]
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    names = {}
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in entry.imports:
            if imp.address is not None:
                names[imp.address] = f"{entry.dll.decode()}!{imp.name.decode() if imp.name else f'ord{imp.ordinal}'}"
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for va in targets:
        rva = va - base
        fo = None
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                fo = s.PointerToRawData + (rva - s.VirtualAddress)
                break
        if fo is None:
            print(f"0x{va:x} section 外")
            continue
        ins = next(md.disasm(raw[fo:fo + 16], va), None)
        if ins and ins.mnemonic == "jmp" and ins.op_str.startswith("qword ptr [rip"):
            disp = int(ins.op_str.split("+")[1].rstrip("]").strip(), 16) if "+" in ins.op_str else -int(ins.op_str.split("-")[1].rstrip("]").strip(), 16)
            slot = ins.address + ins.size + disp
            print(f"0x{va:x} thunk -> slot 0x{slot:x} -> {names.get(slot, '未同定')}")
        elif va in names:
            print(f"0x{va:x} IAT slot -> {names[va]}")
        else:
            print(f"0x{va:x} thunk/slot 以外 ({ins.mnemonic if ins else '?'} {ins.op_str if ins else ''})")


if __name__ == "__main__":
    main()
