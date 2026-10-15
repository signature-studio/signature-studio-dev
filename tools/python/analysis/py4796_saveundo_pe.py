#!/usr/bin/env python3
"""PY-385 (#4796): REPORT_PY124.md §4-2b の未確定項目のうち、PE から確定した事実を検査する (実機不要)。

  FL_WIN64_DIR=<展開先> python3 analysis/py4796_saveundo_pe.py

PE は fl-win64 素材の extracted/block00031_PE.bin (ImageBase 0x400000)。
全検査が通れば PASS を出し、外れれば AssertionError で止まる。
"""
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
UTF8_CP = 0xFDE9
REGISTRY_FILL = 0x102CA60
REGISTRY_ELEM = 0x102B8B0
FACTORY = 0x448EE0
MBTWC_WRAP = 0x41C360
EMPTY_NAME = 0x414850
STR_ASSIGN = 0x414AD0


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(PE, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def off(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def insns(va, n=0x800):
        return list(md.disasm(data[off(va):off(va) + n], va))

    def rip_target(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    # 0x41c360: UTF-8 (CP 65001) を MultiByteToWideChar 系 helper 0x41c930 へ渡す。
    mb = insns(MBTWC_WRAP, 0x200)
    assert any(i.mnemonic == "mov" and i.op_str == f"ecx, {UTF8_CP:#x}" for i in mb), "0x41c360 CP_UTF8"
    assert any(i.mnemonic == "call" and i.op_str == "0x41c930" for i in mb), "0x41c360 helper"
    print("0x41c360 = UTF-8 → UTF-16 変換 (CP 65001 を 0x41c930 へ渡す)")

    # 0x414850: rcx が NULL なら [global]+0x10 (既定の空文字列) を返し、非 NULL なら rcx をそのまま返す。
    em = insns(EMPTY_NAME, 0x20)
    assert em[0].mnemonic == "mov" and em[0].op_str == "rax, rcx"
    assert any(i.mnemonic == "lea" and i.op_str == "rax, [rax + 0x10]" for i in em), "0x414850 +0x10"
    print("0x414850 = NULL なら既定の空文字列 ([global]+0x10)、そうでなければ rcx をそのまま返す")

    # 0x414ad0: 文字列バッファの再利用。[rax-8] (refcount 相当) == 1 かつ [rax-4] == 要求長なら再利用する。
    sa = insns(STR_ASSIGN, 0x80)
    assert any(i.mnemonic == "cmp" and i.op_str == "dword ptr [rax - 8], 1" for i in sa), "0x414ad0 refcnt==1"
    assert any(i.mnemonic == "cmp" and i.op_str == "dword ptr [rax - 4], esi" for i in sa), "0x414ad0 len==n"
    print("0x414ad0 = 文字列バッファの再利用判定 ([-8]==1 かつ [-4]==要求長)")

    # 0x102ca60: registry の flags の bit0 / bit1 が、0x448ee0 へ渡す global とその名前を決める。
    fill = insns(REGISTRY_FILL, 0x200)
    calls = [i for i in fill if i.mnemonic == "call" and i.op_str == f"{FACTORY:#x}"]
    assert len(calls) == 2, [hex(i.address) for i in calls]
    guards, rcx_globals, r8_globals = [], [], []
    for c in calls:
        prev = [i for i in fill if i.address < c.address][-8:]
        rcx = [i for i in prev if i.mnemonic == "mov" and i.op_str.startswith("rcx, qword ptr [rip")]
        r8 = [i for i in prev if i.mnemonic == "mov" and i.op_str.startswith("r8, qword ptr [rip")]
        assert rcx and r8, hex(c.address)
        rcx_globals.append(rip_target(rcx[-1]))
        r8_globals.append(rip_target(r8[-1]))
    for i in fill:
        if i.mnemonic == "mov" and i.op_str.startswith("rax, qword ptr [rip"):
            guards.append(rip_target(i))
    assert rcx_globals[0] == rcx_globals[1] == 0x430DF0, [hex(g) for g in rcx_globals]
    assert r8_globals[0] == r8_globals[1] == 0x15E4C18, [hex(g) for g in r8_globals]
    assert 0x100C1B0 in guards and 0x100D098 in guards, [hex(g) for g in guards]
    print("0x102ca60: bit0 / bit1 の factory 呼出しは第 1 引数 0x430df0・名前 [0x15e4c18] が同じで、guard が違う (0x100c1b0 / 0x100d098。先頭バイト 7 なら呼ばない)")

    # 0x448ee0 は factory: dl が 0 でなければ 0x410320 (vtbl[-0x30] 経由) を呼ぶ。
    fac = insns(FACTORY, 0x80)
    assert any(i.mnemonic == "call" and i.op_str == "0x41c820" for i in fac), "0x448ee0 → 0x41c820 (name 設定)"
    assert any(i.mnemonic == "call" and i.op_str == "0x410320" for i in fac), "0x448ee0 → 0x410320"
    print("0x448ee0 = factory (0x410320 で生成、0x41c820 で name を設定)")

    # 0x102b8b0 (registry 要素の登録): r8 と r9 を 0x41a7b0 と 0x102b3e0 に渡す。
    reg = insns(REGISTRY_ELEM, 0x200)
    assert any(i.mnemonic == "call" and i.op_str == "0x41a7b0" for i in reg), "0x102b8b0 → 0x41a7b0"
    assert any(i.mnemonic == "call" and i.op_str == "0x102b3e0" for i in reg), "0x102b8b0 → 0x102b3e0"
    print("0x102b8b0 = registry 要素の登録 (0x41a7b0 と 0x102b3e0 を呼ぶ)")

    print("PASS: py4796 saveUndo PE facts (PY-385)")


if __name__ == "__main__":
    main()
