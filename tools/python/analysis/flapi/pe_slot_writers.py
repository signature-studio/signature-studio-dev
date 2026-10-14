#!/usr/bin/env python3
"""グローバルのポインタスロット (RIP 相対) を読んだ後、その値を基底にした書込み命令を列挙する (PY-93 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot_writers.py <slot VA(16進)> [disp(16進)]

- slot VA: `mov reg, qword ptr [rip+X]` で読まれるポインタ変数の VA (例: 15e04a8 = flagA のポインタ)。
- disp: 指す先からのオフセット。省略時は 0 (`[reg]` と `[reg+0]` の書込みを対象にする)。
- 各ロード地点から最大 40 命令を線形に追い、基底レジスタ (と mov reg,reg の別名) が `[base+disp]` で書かれる命令を出す。
  別名が上書きされた時点、ret/jmp/call で追跡を止める (呼出し先の副作用は見ない)。
- スロット自体への RIP 相対 store も併せて出す (ポインタの書換え)。

限界: 関数の引数で渡ったポインタ経由の書込みと、絶対アドレス指定の書込みは見ない。結果は候補であり、書込み元の確定は命令の読解で行う。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
WINDOW = 40
WRITE_MNEMONICS = ("mov", "set", "and", "or", "add", "sub", "xor", "inc", "dec", "neg", "not", "xchg")
STOP = ("ret", "jmp", "call", "int3")


def main():
    slot = int(sys.argv[1], 16)
    disp = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    loads, slot_stores = [], []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            ins = next(md.disasm(data[off:off + 16], start + off), None)
            if ins is None:
                off += 1
                continue
            for i, op in enumerate(ins.operands):
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    if ins.address + ins.size + op.mem.disp == slot:
                        if i == 0 and ins.mnemonic == "mov":
                            slot_stores.append((ins.address, f"{ins.mnemonic} {ins.op_str}"))
                        elif ins.mnemonic == "mov" and i == 1:
                            loads.append((ins.address, ins.reg_name(ins.operands[0].reg)))
            off += ins.size
    print(f"slot {hex(slot)} loads {len(loads)} slot_stores {len(slot_stores)}")
    for va, s in slot_stores:
        print(f"SLOT-STORE {hex(va)} {s}")
    for la, reg in loads:
        code = raw[pe.get_offset_from_rva(la - base):pe.get_offset_from_rva(la - base) + 16 * WINDOW]
        regs = {reg}
        for ins in md.disasm(code, la):
            if ins.address == la:
                continue
            mn = ins.mnemonic
            if mn in STOP:
                break
            ops = ins.operands
            if ops and ops[0].type == capstone.x86.X86_OP_MEM and mn.startswith(WRITE_MNEMONICS):
                m = ops[0].mem
                if ins.reg_name(m.base) in regs and m.disp == disp and m.index == 0:
                    print(f"WRITE load={hex(la)}({reg}) {hex(ins.address)} {mn} {ins.op_str}")
            if ops and ops[0].type == capstone.x86.X86_OP_REG:
                dst = ins.reg_name(ops[0].reg)
                if mn == "mov" and len(ops) == 2 and ops[1].type == capstone.x86.X86_OP_REG and ins.reg_name(ops[1].reg) in regs:
                    regs.add(dst)
                else:
                    regs.discard(dst)
                if not regs:
                    break


if __name__ == "__main__":
    main()
