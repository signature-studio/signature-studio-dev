#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の 0x1051720 状態 bb の生成元 (PY-176 / #3253) の主張を再検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_bb_state_probe.py

REPORT_PY176.md の主張を PE 上で照合する: 呼出し先の並び (10519c6 枝)・RIP 参照先の slot (K・V・表 T0・第 2 表・G)・
bb の初期値 0xff・0xf8e4e0 の vtable +0x18 呼出し 2 件・11f1a20 の大域 (文字列・フラグ)。
不一致が 1 つでもあれば終了 1。
"""
import os
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


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    return raw, pe.OPTIONAL_HEADER.ImageBase, pe.sections


def insns(raw, base, secs, va, count):
    rva = va - base
    fo = None
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            fo = s.PointerToRawData + (rva - s.VirtualAddress)
            break
    if fo is None:
        sys.exit(f"VA {va:#x} が section 外")
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
    print(f"summary: {'OK' if fails == 0 else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
