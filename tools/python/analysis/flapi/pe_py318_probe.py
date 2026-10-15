#!/usr/bin/env python3
"""PY-318 (#4337): 0x45c290 の変換 helper (0x45c170・0x45c040・0x45c1c0) の間接 call 先の確定 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py318_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。ネガティブコントロールは「期待が偽」を PASS とする。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def fo_of(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"VA {va:#x} が section 外")

    def qword(va):
        return struct.unpack_from("<Q", raw, fo_of(va))[0]

    def wstr(va):
        o, out = fo_of(va), b""
        while raw[o:o + 2] != b"\x00\x00":
            out += raw[o:o + 2]
            o += 2
        return out.decode("utf-16-le")

    def cstr(va):
        o = fo_of(va)
        return raw[o:raw.index(b"\x00", o)].decode(errors="replace")

    def decode(start, end):
        return list(md.disasm(raw[fo_of(start):fo_of(start) + (end - start)], start))

    def rip_ea(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    imports = {}
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in entry.imports:
            if imp.address is not None and imp.name:
                imports[imp.address] = f"{entry.dll.decode()}!{imp.name.decode()}"

    def thunk_target(va):
        ins = decode(va, va + 6)[0]
        ea = rip_ea(ins)
        return imports.get(ea) if ea is not None and ins.mnemonic == "jmp" else None

    # 1. 0x457c70 (初期化): oleaut32 の関数名を GetProcAddress で解決し .bss セルへ格納する
    init = decode(0x457C70, 0x457CC2)
    stores = {rip_ea(i): i.address for i in init if i.mnemonic == "mov" and i.op_str.startswith("qword ptr [rip") and "rax" in i.op_str}
    check("0x457c70: GetModuleHandleW thunk (0x4235b0)", thunk_target(0x4235B0) == "kernel32.dll!GetModuleHandleW")
    check("0x4235e0 thunk は GetProcAddress", thunk_target(0x4235E0) == "kernel32.dll!GetProcAddress")
    check("0x457c78: モジュール名 = oleaut32.dll", wstr(0x457F0C) == "oleaut32.dll", wstr(0x457F0C))
    check("0x457c8b: 名前 = VariantChangeTypeEx", cstr(0x457F26) == "VariantChangeTypeEx", cstr(0x457F26))
    check("0x457c9e: 解決結果を .bss セル 0x15f1038 へ格納", 0x15F1038 in stores, hex(stores.get(0x15F1038, 0)))

    # 2. 0x45c170 の間接 call [rax]: rax = [slot 0x15e3ea8] = セル 0x15f1038
    w = decode(0x45C170, 0x45C1C0)
    idx = [i for i, x in enumerate(w) if x.mnemonic == "call" and x.op_str == "qword ptr [rax]"]
    slot_ea = rip_ea(w[idx[0] - 1]) if idx else None
    check("0x45c170: 間接 call [rax] (rax は mov rax,[rip+X])", bool(idx) and w[idx[0] - 1].mnemonic == "mov", hex(slot_ea or 0))
    check("slot 0x15e3ea8 の値 = セル 0x15f1038", slot_ea == 0x15E3EA8 and qword(slot_ea) == 0x15F1038, hex(qword(slot_ea)) if slot_ea else "")
    check("0x45c170 の引数: lcid 0x400, vt 3 (VT_I4)", any(x.op_str == "r8d, 0x400" for x in w) and any(x.op_str == "word ptr [rsp + 0x20], 3" for x in w))

    # 3. 0x45c040 の間接 call [rax]: rax = [slot 0x15e4a68] = セル 0x15f10a0 = VarI4FromStr
    x40 = decode(0x45C040, 0x45C0C0)
    idx40 = [i for i, x in enumerate(x40) if x.mnemonic == "call" and x.op_str == "qword ptr [rax]"]
    slot40 = rip_ea(x40[idx40[0] - 1]) if idx40 else None
    check("0x45c040: 間接 call [rax] の slot 0x15e4a68 = セル 0x15f10a0", slot40 == 0x15E4A68 and qword(slot40) == 0x15F10A0, hex(qword(slot40)) if slot40 else "")
    check("0x457e17 の store が 0x15f10a0 へ格納 (48 89 05 形)", raw[fo_of(0x457E17):fo_of(0x457E17) + 3] == b"\x48\x89\x05" and
          (0x457E17 + 7 + struct.unpack_from("<i", raw, fo_of(0x457E17) + 3)[0]) == 0x15F10A0)
    check("0x457e0b: 名前 = VarI4FromStr", cstr(0x457F8E) == "VarI4FromStr", cstr(0x457F8E))

    # 4. 0x45c1c0 の間接 call [rip+X]: セル 0x15f1100 = 0x45a050 (lea で求めた値)
    c = decode(0x45C1C0, 0x45C210)
    call_1c0 = [x for x in c if x.mnemonic == "call" and "rip" in x.op_str]
    ea1c0 = rip_ea(call_1c0[0]) if call_1c0 else None
    check("0x45c1c0: 間接 call [rip+X] の先 = セル 0x15f1100", ea1c0 == 0x15F1100, hex(ea1c0 or 0))
    init2 = decode(0x467F00, 0x467F50)
    lea_val = {i.address: rip_ea(i) for i in init2 if i.mnemonic == "lea" and rip_ea(i)}
    store1c0 = [i for i in init2 if i.mnemonic == "mov" and rip_ea(i) == 0x15F1100]
    check("0x467f40: セル 0x15f1100 へ rcx を格納", bool(store1c0) and store1c0[0].op_str.endswith("], rcx"))
    check("0x467f39: rcx = lea → 0x45a050", 0x45A050 in lea_val.values(), hex(0x45A050))

    # 5. 0x7ffdfffb と 0x80020005 の関係 (算術の確認)
    check("0x7ffdfffb = -0x80020005 (mod 2^32): 加算で 0", (0x7FFDFFFB + 0x80020005) & 0xFFFFFFFF == 0)

    # ネガティブ対照: 0x45c170 の slot は 0x15f1100 ではない / 0x45c040 は VT_I4 の式ではない
    check("ネガティブ: 0x45c170 の slot を 0x15f1100 と誤認した期待は偽", slot_ea != 0x15F1100)
    check("ネガティブ: 0x45c040 の名前を VariantChangeTypeEx と誤認した期待は偽", cstr(0x457F8E) != "VariantChangeTypeEx")

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} PASS")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
