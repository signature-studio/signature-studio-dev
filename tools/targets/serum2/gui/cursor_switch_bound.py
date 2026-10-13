#!/usr/bin/env python3
"""cursor_switch_scan.py が見つけた IDC_SIZEALL 含有関数の先頭を逆アセンブルし、
switch の範囲検査 (cmp reg, imm / ja / jmp [table]) を列挙する。

入力: work/Serum2_win64.vst3 (REPORT §9-1 で展開)。
引数: 関数開始 RVA (16 進, 例 0x172800)。
"""
import sys

import capstone
import pefile

BIN = "work/Serum2_win64.vst3"


def main():
    start_rva = int(sys.argv[1], 16)
    end_rva = int(sys.argv[2], 16)
    pe = pefile.PE(BIN, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    data = text.get_data()
    off0 = start_rva - text.VirtualAddress
    off1 = end_rva - text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i in md.disasm(data[off0:off1], base + start_rva):
        s = f"{i.address - base:x}: {i.mnemonic} {i.op_str}"
        if i.mnemonic in ("cmp", "ja", "jbe", "jmp", "lea") or "[" in i.op_str and "rip" in i.op_str:
            print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
