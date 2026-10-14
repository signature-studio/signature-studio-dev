#!/usr/bin/env python3
"""指定 VA 範囲の RIP 相対オペランドを解決し、スロット VA・所属 section・ファイル上の実バイトを出す (PY-92 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flag_slots.py <開始VA(16進)> <終了VA(16進)>

既定の対象は 0x104d0d0 (事象 flags 分類器) の範囲 0x104d0d0-0x104d290。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    lo, hi = (int(x, 16) for x in sys.argv[1:3])
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def read_va(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                name = s.Name.rstrip(b"\0").decode()
                if rva - s.VirtualAddress >= s.SizeOfRawData:
                    return None, name
                fo = s.PointerToRawData + (rva - s.VirtualAddress)
                return raw[fo:fo + n], name
        return None, "?"

    code, _ = read_va(lo, hi - lo)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for ins in md.disasm(code, lo):
        for op in ins.operands:
            if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
                continue
            tgt = ins.address + ins.size + op.mem.disp
            data, sec = read_va(tgt, 1)
            print(f"0x{ins.address:x} {ins.mnemonic} {ins.op_str} -> slot 0x{tgt:x} ({sec}) byte={data.hex() if data else None}")


if __name__ == "__main__":
    main()
