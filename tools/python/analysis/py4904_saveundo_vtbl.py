#!/usr/bin/env python3
"""PY-4904 (#5292): general.saveUndo の vtbl 3 本 (+0x10・+0x18・+0x40) の呼出し箇所を検査する (実機不要)。

  FL_WIN64_DIR=<展開先> python3 analysis/py4904_saveundo_vtbl.py

PE は fl-win64 素材の extracted/block00031_PE.bin (ImageBase 0x400000)。
検査する事実は REPORT_PY124.md §4-2c の表と 1 対 1 に対応する。
vtbl の実体 (型) は PE の静的な読みでは決まらないので、ここでは検査しない (理由は REPORT)。
全検査が通れば PASS を出し、外れれば AssertionError で止まる。
"""
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CALLS_VTBL_10 = (0x101B8F6, 0x101BC1F)  # call [rbx+0x10]
CALLS_VTBL_40 = (0x101B98E, 0x101B9D4)  # call [rbx+0x40]
PROBE_VTBL_18 = 0x102B690               # call [rax+0x18] (vtbl+0x18(value, c))


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(PE, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def at(va):
        off = text.PointerToRawData + (va - base - text.VirtualAddress)
        return next(md.disasm(data[off:off + 16], va))

    for va in CALLS_VTBL_10:
        ins = at(va)
        assert ins.mnemonic == "call" and ins.op_str == "qword ptr [rbx + 0x10]", (hex(va), ins.op_str)
    print("vtbl+0x10 呼出し: 0x101b8f6 / 0x101bc1f (call [rbx+0x10])")

    for va in CALLS_VTBL_40:
        ins = at(va)
        assert ins.mnemonic == "call" and ins.op_str == "qword ptr [rbx + 0x40]", (hex(va), ins.op_str)
    print("vtbl+0x40 呼出し: 0x101b98e (record+0x0c) / 0x101b9d4 (record+0x14)")

    ins = at(PROBE_VTBL_18)
    assert ins.mnemonic == "call" and ins.op_str == "qword ptr [rax + 0x18]", ins.op_str
    print("vtbl+0x18 呼出し: 0x102b690 (this = registry+0x18 の object、dl = entry byte、r8d = c)")

    print("PASS: py4904 saveUndo vtbl call sites")


if __name__ == "__main__":
    main()
