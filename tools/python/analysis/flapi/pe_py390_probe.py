#!/usr/bin/env python3
"""findEventID (fl_table 331) と isDoubleClick (fl_table 348) の戻り値・status 経路を FLEngine PE で再確認する (PY-390 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py390_probe.py

REPORT_PY390.md §1 で読んだ分岐を、命令と call 先の assert で固定する。assert が落ちたら PE が変わっている。
展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先>
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def v2o(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        sys.exit(f"VA {va:#x} が section 外")

    def disasm(va, n):
        return {i.address: i for i in md.disasm(raw[v2o(va):v2o(va) + n * 16], va)}

    fails = []

    def check(cond, msg):
        print(("OK   " if cond else "FAIL ") + msg)
        if not cond:
            fails.append(msg)

    def op(ins, va):
        return f"{ins[va].mnemonic} {ins[va].op_str}" if va in ins else "(missing)"

    fe = disasm(0xD75B60, 40)
    check(op(fe, 0xD75B98) == "call 0xf8c8e0", "findEventID 0xd75b98: 成功時 helper 0xf8c8e0 を呼ぶ")
    check(op(fe, 0xD75BAC) == "call 0xd82c20", "findEventID 0xd75bac: 失敗時 0xd82c20(eax) を呼ぶ")
    check(raw[v2o(0xD75BB8):v2o(0xD75BB8) + 4] == b"i|i\x00", "findEventID PyArg 書式 'i|i' (0xd75bb8)")

    ic = disasm(0xD76060, 75)
    check(op(ic, 0xD76109) == "call 0xd843d0", "isDoubleClick 0xd76109: dispatch 0xd843d0 を呼ぶ")
    check(op(ic, 0xD76118) == "jne 0xd7612f", "isDoubleClick 0xd76118: status ≠ 0 は 0xd7612f へ")
    check(op(ic, 0xD7611A) == "mov ecx, dword ptr [rbp + 0x88]", "isDoubleClick 0xd7611a: status 0 のとき [rbp+0x88] を変換器へ")
    check(op(ic, 0xD7612F) == "mov ecx, eax", "isDoubleClick 0xd7612f: status 経路は 0xd82c20 へ渡す")
    check(raw[v2o(0xD76184):v2o(0xD76184) + 2] == b"i\x00", "isDoubleClick PyArg 書式 'i' (0xd76184)")

    ds = disasm(0xD843D0, 12)
    check(op(ds, 0xD843E9) == "mov qword ptr [rsi], 0xfffffffffffffffe", "dispatch 0xd843d0: 結果 status の初期値 -2")

    core = disasm(0xD76000, 25)
    check(op(core, 0xD76010) == "call 0x11d1430", "core 0xd76000: 準備判定 0x11d1430 を呼ぶ")
    check(op(core, 0xD76019) == "mov qword ptr [rbx + 0x60], 0", "core 0xd76019: 準備 OK で status 0")
    check(op(core, 0xD76047) == "mov qword ptr [rbx + 0x60], 0xfffffffffffffff9",
          "core 0xd76047: device 無しで status -7")

    rd = disasm(0x11D1430, 8)
    check(op(rd, 0x11D1448) == "call qword ptr [rax + 0x88]", "0x11d1430: vtbl+0x88 を呼ぶ (準備判定)")

    st = disasm(0xD82C20, 40)
    check(op(st, 0xD82C7E) == "call qword ptr [rax + 0x88]", "d82c20 0xd82c7e: 報告判定 vtbl+0x88 (REPORT_PY61 §4-1)")

    if fails:
        sys.exit(f"{len(fails)} 件失敗")
    print("all checks passed")


if __name__ == "__main__":
    main()
