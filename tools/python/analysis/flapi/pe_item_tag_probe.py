#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の item tag 解決 (PY-195 / #3403) の主張を PE 上で再検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_item_tag_probe.py

検査するのは次の 2 種だけ (命令の存在検査と大域スロットの値検査):
- 命令: 0xf8ca50 の 3 分岐 (high16 == 0xfff・top10 == 0xff)・0x11e83d0 の L1 走査 (+0x2f8 比較)・
  0x11e8280 の L2 走査 (+0x32c 比較・+0x794 の読出し)・大域 P (0x15e26a0) の書込み 2 箇所と読出し 1 箇所。
- 大域: L1 スロット 0x15e2218・L2 スロット 0x15e0128・P スロット 0x15e26a0 の .data 上の初期値 (ポインタ先)。
検査しない: 分岐の意味づけ (L1 が global channel 列・+0x2f8 が MIDI 入力ポート) と、P の書込み値の出どころ。
不一致が 1 つでもあれば終了 1。
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")

RIP_RE = re.compile(r"\[rip \+ (0x[0-9a-f]+)\]")

# (VA, 期待する命令の文字列 "mnemonic op_str"。RIP 参照は解決先 VA を期待値に書く)
INSNS = [
    (0xF8CA60, "cmp edx, 0xfff"),
    (0xF8CA9A, "cmp eax, 0xff"),
    (0xF8CAA1, "mov rax, qword ptr [rip + 0x655bf8]"),
    (0xF8CAA8, "mov ebx, dword ptr [rax]"),
    (0xF8CA79, "call 0x11e83d0"),
    (0xF8CA8A, "call 0x11e8280"),
    (0x11E83E4, "mov rcx, qword ptr [rip + 0x3f9e2d]"),
    (0x11E8415, "cmp dword ptr [rax + 0x2f8], ebx"),
    (0x11E8299, "mov rcx, qword ptr [rip + 0x3f7e88]"),
    (0x11E82CC, "cmp byte ptr [rax + 0x32c], 0"),
    (0x11E8360, "mov rax, qword ptr [rip + 0x3f7dc1]"),
    (0x11E8371, "mov eax, dword ptr [rax + 0x794]"),
    (0x12900CA, "mov rax, qword ptr [rip + 0x3525cf]"),
    (0x12900D7, "mov dword ptr [rax], ecx"),
    (0x12A4583, "mov rax, qword ptr [rip + 0x33e116]"),
    (0x12A458D, "mov dword ptr [rax], ecx"),
    (0x12C1967, "movsxd rdx, dword ptr [rip + 0x67e0a2]"),
]

# (スロット VA, 期待するポインタ先 VA)。.data 上の初期値。
SLOTS = [
    (0x15E2218, 0x16BAFC8),
    (0x15E0128, 0x16BAFD0),
    (0x15E26A0, 0x193FA10),
]

# 期待する RIP 参照先 (上の INSNS の RIP 命令の解決先)
RIP_TARGETS = {
    0x11E83E4: 0x15E2218,
    0x11E8299: 0x15E0128,
    0x11E8360: 0x15E0128,
    0xF8CAA1: 0x15E26A0,
    0x12900CA: 0x15E26A0,
    0x12A4583: 0x15E26A0,
    0x12C1967: 0x193FA10,
}


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    fails = 0

    def fo_of(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                if rva - s.VirtualAddress >= s.SizeOfRawData:
                    return None, s.Name.rstrip(b"\0").decode()
                return s.PointerToRawData + (rva - s.VirtualAddress), s.Name.rstrip(b"\0").decode()
        return None, None

    for va, want in INSNS:
        fo, _ = fo_of(va)
        ins = next(md.disasm(raw[fo:fo + 16], va))
        got = f"{ins.mnemonic} {ins.op_str}".strip()
        ok = got == want
        if va in RIP_TARGETS and ok:
            m = RIP_RE.search(ins.op_str)
            tgt = va + ins.size + int(m.group(1), 16)
            ok = tgt == RIP_TARGETS[va]
            got = f"{got} -> {tgt:#x}"
        fails += 0 if ok else 1
        print(("PASS" if ok else "FAIL"), f"{va:#x} {want}", "" if ok else f"(got: {got})")

    for slot, want in SLOTS:
        fo, name = fo_of(slot)
        val = struct.unpack_from("<Q", raw, fo)[0]
        ok = val == want
        fails += 0 if ok else 1
        print(("PASS" if ok else "FAIL"), f"slot {slot:#x} ({name}) -> {val:#x}", "" if ok else f"(want {want:#x})")

    print("summary:", "OK" if fails == 0 else f"{fails} FAIL")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
