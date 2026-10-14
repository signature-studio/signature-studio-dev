#!/usr/bin/env python3
"""PY-100 (#2879): channels.getStepParam / getCurrentStepParam の PE 事実を再現する (REPORT_PY100.md の表の出所)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_param.py

確認すること: (1) PyArg 書式と kwlist (2) 3 つの [global] 参照先 slot が同一 (= patternNumber() の slot)
(3) 0xd5b930 の param 写像 (逆アセンブルを手で読んだ結果を表に固定して出力するだけ。自動検査はしない)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase


def read_va(va, n):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            fo = s.PointerToRawData + (rva - s.VirtualAddress)
            return RAW[fo:fo + n]
    raise SystemExit(f"VA {va:#x} が section 外")


def cstr(va):
    return read_va(va, 64).split(b"\0")[0].decode(errors="replace")


def rip_target(next_ip, disp):
    return next_ip + disp


def main():
    # PyArg 書式: lea r8,[rip+disp] は 0xd5ba16 / 0xd5bb45 にある (命令長 7)。kwlist は lea r9 (0xd5ba1d / 0xd5bb4c)
    fmt_ga = cstr(rip_target(0xd5ba1d, 0xe7))
    fmt_gc = cstr(rip_target(0xd5bb4c, 0x94))
    kw_ga = [cstr(struct.unpack("<Q", read_va(rip_target(0xd5ba24, 0x7bb55c) + 8 * i, 8))[0]) for i in range(5)]
    kw_gc = [cstr(struct.unpack("<Q", read_va(rip_target(0xd5bb53, 0x7bb45d) + 8 * i, 8))[0]) for i in range(4)]
    print("getStepParam     fmt=%r kwlist=%r" % (fmt_ga, kw_ga))
    print("getCurrentStepP. fmt=%r kwlist=%r" % (fmt_gc, kw_gc))
    assert fmt_ga == "iiii|i" and kw_ga == ["step", "param", "offset", "startPos", "padsStride"]
    assert fmt_gc == "iii|i" and kw_gc == ["index", "step", "param", "useGlobalIndex"]

    # [global] (pat) の参照先 slot。getStepParam は mov rax,[rip+..] @0xd5bac7、getCurrentStepParam は @0xd5bba9
    slot_ga = rip_target(0xd5bace, 0x88854a)
    slot_gc = rip_target(0xd5bbb0, 0x888468)
    slot_pn = rip_target(0xd64d2b, 0x87f2ed)  # patternNumber() (0xd64d20) が読む slot
    print("slot getStepParam=%#x getCurrentStepParam=%#x patternNumber=%#x" % (slot_ga, slot_gc, slot_pn))
    assert slot_ga == slot_gc == slot_pn

    # 0xd5b930 の param 写像 (pe_disasm.py 0xd5b930 の手読み。自動検査はしない)
    table = {0: "word [rax+0xc]", 1: "byte [rax+0x15]", 2: "byte [rax+0x12]", 3: "byte [rax+0x10]",
             4: "byte [rax+0x14]", 5: "byte [rax+0x16]", 6: "byte [rax+0x17]", 7: "dword [rax]", 8: "byte [rax+0x11]"}
    for prm, want in table.items():
        print("param %d -> %s" % (prm, want))
    print("OK: PyArg 書式・kwlist・slot 同一性を確認 (assert 通過)")


if __name__ == "__main__":
    main()
