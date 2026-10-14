#!/usr/bin/env python3
"""VSTGUI 14.0 と 14.1 以降を分ける D2DFont の CustomFonts 構築の一致判定 (#1350)。

14.0 の d2dfont.cpp は getCustomFonts() の中で std::call_once により CustomFonts を構築する。
14.1 以降は call_once が無く D2DFont::initialize() で直接構築する (vstgui4 タグで確認)。
バイナリ側で「"Fonts\\*" を組み立てる関数」が InitOnceBeginInitialize の直後の経路で
呼ばれていれば、14.0 の構造と整合する。

入力: work/Serum2_win64.vst3 (REPORT §9-1 で展開)。
出力: "Fonts\\*" 文字列の RVA、その参照元関数、InitOnceBeginInitialize の呼び出し元と
      その直後 0x40 B 以内の直接 call 先。
"""
import re
import sys

import capstone
import pefile

BIN = "work/Serum2_win64.vst3"
WINDOW = 0x40


def main():
    pe = pefile.PE(BIN, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    sections = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sections[b".text"]
    data = text.get_data()
    tva = text.VirtualAddress

    iat = {}
    for ent in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in ent.imports:
            if imp.name:
                iat[imp.address] = imp.name.decode()

    raw = open(BIN, "rb").read()
    strs = []
    for m in re.finditer(rb"Fonts\\\*", raw):
        for s in pe.sections:
            if s.PointerToRawData <= m.start() < s.PointerToRawData + s.SizeOfRawData:
                strs.append(s.VirtualAddress + m.start() - s.PointerToRawData)
    print("Fonts* string RVA:", [hex(x) for x in strs])

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    ref_funcs = set()
    init_begin = []
    insns = list(md.disasm(data, base + tva))
    for i in insns:
        for op in i.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                ea = i.address + i.size + op.mem.disp - base
                if ea in strs:
                    ref_funcs.add(hex(i.address - base))
    thunk_rva = set()
    for i in insns:
        if i.mnemonic == "jmp":
            for op in i.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    ea = i.address + i.size + op.mem.disp
                    if iat.get(ea) == "InitOnceBeginInitialize":
                        thunk_rva.add(i.address - base)
    for i in insns:
        if i.mnemonic == "call":
            for op in i.operands:
                if op.type == capstone.x86.X86_OP_IMM and (op.imm - base) in thunk_rva:
                    init_begin.append(i.address - base)
    print("InitOnceBeginInitialize call sites:", [hex(x) for x in init_begin])

    for site in init_begin:
        off = site - tva
        targets = []
        for i in md.disasm(data[off:off + WINDOW + 0x10], base + site):
            if i.address - base > site + WINDOW:
                break
            if i.mnemonic == "call":
                for op in i.operands:
                    if op.type == capstone.x86.X86_OP_IMM:
                        targets.append(op.imm - base)
        print(f"  site {hex(site)} -> direct calls within +0x40: {[hex(t) for t in targets]}")
    print("Fonts* referencing instructions:", sorted(ref_funcs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
