#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の 0x1051720 状態 bb の生成元 (PY-176 / #3253) の主張を PE 上で再検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_bb_state_probe.py

検査するのは次の 3 種だけ (構造の存在検査・定数の値検査・literal の全文検査):
- 構造: 10519c6 枝の呼出し先の並び・RIP 参照先の slot (G・K・V・第 2 表・表 T0・文字列・フラグ)・
  bb の初期値 0xff (0x105180d)・0xf82c20 が 0xf8e4e0 を呼ぶこと・0xf8e4e0 が vtable +0x18 を 2 回呼ぶこと。
- 定数: 0x1051b78 (f64 0.05)・0x1051b80 (f64 100.0)・0x1051be0 (byte 0)。
- literal: UTF-16LE で NUL 終端まで読んだ全文 (0x1051bf0 ほか 5 件)。
検査しない: decode 規則 (0xf829c0)・0x1051720 の分岐条件・REPORT の推論そのもの。
不一致が 1 つでもあれば終了 1。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")

CALLER = 0x1051720
SET_BB = 0xF82A10
NOTIFY = 0xF82C20
BRANCH_LO, BRANCH_HI = 0x10519C6, 0x1051B74
BRANCH_CALLS = [0x104F580, 0x414C70, 0x104D2B0, 0x104D2B0, 0x414E70, 0x43DD60, 0x414C70,
                0x414DA0, 0x414DA0, 0x11F1A20, 0x412E40, 0x412E40]
SLOT_K, SLOT_V, SLOT_T0, SLOT_T1, SLOT_G = 0x16BACF0, 0x16BACEC, 0x16BACD8, 0x15E47E8, 0x15E0A00
SLOT_MSG, SLOT_FLAG = 0x16BD1A0, 0x16BD1A8
DISPATCH = 0xF8E4E0
CONSTS = [
    (0x1051B78, "<d", 0.05, "定数 0x1051b78 = 0.05 (f64)"),
    (0x1051B80, "<d", 100.0, "定数 0x1051b80 = 100.0 (f64)"),
    (0x1051BE0, "<B", 0, "定数 0x1051be0 = 0 (byte)"),
]
LITERALS = [
    (0x1051BF0, " is waiting for pickup: "),
    (0x1051C30, "%.2f"),
    (0x1051C48, "%"),
    (0x1051C58, " "),
    (0x1051C68, " < "),
    (0x1051C7C, " > "),
]


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    return raw, pe.OPTIONAL_HEADER.ImageBase, pe.sections


def file_off(base, secs, va):
    rva = va - base
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def insns(raw, base, secs, va, count):
    fo = file_off(base, secs, va)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = []
    for i, ins in enumerate(md.disasm(raw[fo:fo + count * 16], va)):
        if i >= count:
            break
        rip = None
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                rip = ins.address + ins.size + op.mem.disp
        out.append((ins.address, ins.mnemonic, ins.op_str, rip))
    return out


def wstr(raw, base, secs, va):
    fo = file_off(base, secs, va)
    out = ""
    for i in range(0, 2 * 200, 2):
        u = int.from_bytes(raw[fo + i:fo + i + 2], "little")
        if u == 0:
            return out
        out += chr(u)
    return None


def main():
    raw, base, secs = load()
    fails = 0

    def check(name, ok):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    caller = insns(raw, base, secs, CALLER, 400)
    branch = [int(op, 16) for a, m, op, _ in caller
              if BRANCH_LO <= a <= BRANCH_HI and m == "call" and op.startswith("0x")]
    check("10519c6 枝の呼出し先の並び", branch == BRANCH_CALLS)
    check("bb の初期値 0xff (0x105180d)",
          any(a == 0x105180D and op == "byte ptr [rbp + 0xbb], 0xff" for a, _, op, _ in caller))
    rips = {r for _, _, _, r in caller if r is not None}
    check("G の参照 slot 0x15e0a00", SLOT_G in rips)
    set_bb = insns(raw, base, secs, SET_BB, 400)
    rips = {r for _, _, _, r in set_bb if r is not None}
    check("0xf82a10 の slot: K・V・第 2 表・表 T0",
          {SLOT_K, SLOT_V, SLOT_T1, SLOT_T0} <= rips)
    notify = insns(raw, base, secs, NOTIFY, 150)
    rips = {r for _, _, _, r in notify if r is not None}
    check("0xf82c20 の slot: K・V・表 T0", {SLOT_K, SLOT_V, SLOT_T0} <= rips)
    check("0xf82c20 が 0xf8e4e0 を呼ぶ",
          any(m == "call" and op == f"{DISPATCH:#x}" for _, m, op, _ in notify))
    disp = insns(raw, base, secs, DISPATCH, 80)
    check("0xf8e4e0 が vtable +0x18 を 2 回呼ぶ",
          sum(1 for _, m, op, _ in disp if m == "call" and op.endswith("+ 0x18]")) == 2)
    msg = insns(raw, base, secs, 0x11F1A20, 40)
    rips = {r for _, _, _, r in msg if r is not None}
    check("11f1a20 の slot: 文字列・フラグ", {SLOT_MSG, SLOT_FLAG} <= rips)
    for va, fmt, want, name in CONSTS:
        check(name, struct.unpack_from(fmt, raw, file_off(base, secs, va))[0] == want)
    for va, want in LITERALS:
        check(f"literal {va:#x} = {want!r} (UTF-16LE・NUL 終端)", wstr(raw, base, secs, va) == want)
    print(f"summary: {'OK' if fails == 0 else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
