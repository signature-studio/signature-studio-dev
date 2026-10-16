#!/usr/bin/env python3
"""HeartCore.core_64 の指定 VA 範囲を capstone で逆アセンブルして標準出力に出す (#4917 KH-135)。

  callsite_disasm.py <core.pe> <start_va_hex> <end_va_hex>

呼出し引数の源 (rcx・rdx・r8・r9・[rsp+0x20].. の設定命令) を確かめるための道具。
出力は VA・機械語バイト・命令。範囲は [start, end) で指定する。
"""
import sys

import capstone
import pefile


def main():
    if len(sys.argv) != 4:
        sys.exit('usage: callsite_disasm.py <core.pe> <start_va_hex> <end_va_hex>')
    core, start, end = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    pe = pefile.PE(core, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off = start - base
    code = data[off:end - base]
    for ins in md.disasm(code, start):
        print('%x  %-24s %s %s' % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))


if __name__ == '__main__':
    main()
