#!/usr/bin/env python3
"""FLEngine PE の step 換算値 V (slot 0x15e25f8 の指す int) の解析補助 (PY-185 / #3310。REPORT_PY39_2548.md の節が出所)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_v.py

確認すること: (1) slot 0x15e25f8 の静的値 (.data の初期ポインタ) と指す構造体 T の +0 (X)・+4 (V) の静的値
(2) 更新関数 F=0x13111a0 の呼出し元 (E8 rel32 の線形スキャン) (3) F 内の RIP 相対 store と V = X>>2 の命令列
(4) F の中で候補集合を引く分岐のゲート slot 0x15e13b8 の静的値 (0 なら X は引数のまま)。
出力は PE の静的内容と命令の読み。実行時の値は読まない。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
SLOT = 0x15E25F8
F = 0x13111A0
GATE = 0x15E13B8


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def fo_of(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                return s.PointerToRawData + (rva - s.VirtualAddress), s.Name.rstrip(b"\0").decode()
        return None, None

    def q(va):
        fo, _ = fo_of(va)
        return struct.unpack_from("<Q", raw, fo)[0] if fo is not None else None

    def i(va):
        fo, _ = fo_of(va)
        return struct.unpack_from("<i", raw, fo)[0] if fo is not None else None

    ptr = q(SLOT)
    print(f"slot {SLOT:#x} ({fo_of(SLOT)[1]}) -> {ptr:#x}")
    print(f"  T+0 (X) {ptr - 4:#x} = {i(ptr - 4)}   T+4 (V) {ptr:#x} = {i(ptr)}   T+8 {ptr + 4:#x} = {i(ptr + 4)}")
    print(f"  [0x15d898c] (steps per beat) = {i(0x15D898C)}")
    print(f"gate slot {GATE:#x} ({fo_of(GATE)[1]}) -> {q(GATE):#x}; *gate = {q(q(GATE))}")

    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    tstart = base + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    callers = []
    for off in range(len(data) - 5):
        if data[off] == 0xE8:
            rel = struct.unpack_from("<i", data, off + 1)[0]
            if tstart + off + 5 + rel == F:
                callers.append(tstart + off)
    print(f"callers of F={F:#x}: {len(callers)} -> " + " ".join(f"{c:#x}" for c in callers))

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    fo, _ = fo_of(F)
    print(f"F={F:#x} の RIP 相対オペランドと call (先頭 0x180 バイト):")
    for ins in md.disasm(raw[fo:fo + 0x180], F):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                kind = "store" if ins.operands[0].type == capstone.x86.X86_OP_MEM else "load"
                print(f"  {ins.address:#x} {kind:5s} {ins.mnemonic} {ins.op_str}  -> {tgt:#x} = {i(tgt)}")
        if ins.mnemonic == "call":
            print(f"  {ins.address:#x} call {ins.op_str}")


if __name__ == "__main__":
    main()
