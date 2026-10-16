#!/usr/bin/env python3
"""PY-5356 (#5551): 0x4128b0 末尾の間接 call 先 0x15e6068 の参照元の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5551_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
H = 0x15E6068
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
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    start = text.VirtualAddress + base
    code = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    def rip_ea(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    refs = []
    off = 0
    while off < len(code):
        got = list(md.disasm(code[off:off + 16], start + off, 1))
        if not got:
            off += 1
            continue
        if rip_ea(got[0]) == H:
            refs.append(got[0])
        off += got[0].size

    # 0x412a01 の間接 call が 0x15e6068 を読む
    call_ins = [i for i in refs if i.address == 0x412A01]
    check("0x412a01: call qword [0x15e6068]", len(call_ins) == 1 and call_ins[0].mnemonic == "call")

    # 0x15e6068 への store (mov [H], reg/imm) が block00031 内に無いこと
    stores = [i for i in refs if i.mnemonic == "mov" and i.operands and i.operands[0].type == capstone.x86.X86_OP_MEM]
    check("0x15e6068 への mov store が block00031 内に 0 件", len(stores) == 0,
          ", ".join(f"0x{i.address:x} {i.mnemonic} {i.op_str}" for i in stores))

    other = [i for i in refs if i.address != 0x412A01]
    check("0x15e6068 の他の参照 (読み・書き) を列挙", True,
          ", ".join(f"0x{i.address:x} {i.mnemonic} {i.op_str}" for i in other) or "0 件")

    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
