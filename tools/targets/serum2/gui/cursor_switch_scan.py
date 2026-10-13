#!/usr/bin/env python3
"""IDC_SIZEALL (0x7F86) を含む関数を特定し、同関数内のカーソル ID 即値 (0x7F00-0x7FFF) を列挙する。

入力: work/Serum2_win64.vst3 (REPORT §9-1 で展開)。
出力: 各ヒットの関数開始 RVA (直前の int3/nop 境界から推定)、関数内の cursor ID 即値の一覧。
"""
import sys
import struct

import capstone
import pefile

BIN = "work/Serum2_win64.vst3"
IDC = {0x7F00: "IDC_ARROW", 0x7F01: "IDC_IBEAM", 0x7F02: "IDC_WAIT", 0x7F03: "IDC_CROSS",
       0x7F04: "IDC_UPARROW", 0x7F80: "IDC_SIZE", 0x7F81: "IDC_ICON", 0x7F82: "IDC_SIZENWSE",
       0x7F83: "IDC_SIZENESW", 0x7F84: "IDC_SIZEWE", 0x7F85: "IDC_SIZENS", 0x7F86: "IDC_SIZEALL",
       0x7F88: "IDC_NO", 0x7F89: "IDC_HAND", 0x7F8A: "IDC_APPSTARTING", 0x7F8B: "IDC_HELP"}


def main():
    pe = pefile.PE(BIN, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    data = text.get_data()
    va0 = text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    hits = [off for off in range(len(data) - 4)
            if struct.unpack_from("<I", data, off)[0] == 0x7F86]
    for off in hits:
        start = off
        while start > 0 and not (data[start - 1] in (0xCC, 0x90) and data[start] not in (0xCC, 0x90)):
            start -= 1
            if off - start > 0x4000:
                break
        end = off
        while end < len(data) - 1 and not (data[end] in (0xCC,) and data[end + 1] == 0xCC):
            end += 1
            if end - off > 0x4000:
                break
        ids = []
        for i in md.disasm(data[start:end], va0 + start):
            if i.mnemonic in ("mov", "lea", "cmp") and "0x7f" in i.op_str:
                for tok in i.op_str.replace(",", " ").split():
                    if tok.startswith("0x7f"):
                        v = int(tok, 16)
                        if 0x7F00 <= v <= 0x7FFF:
                            ids.append((hex(i.address), v))
        print(f"hit RVA 0x{va0 + off:x}: func 0x{va0 + start:x}..0x{va0 + end:x} "
              f"({end - start} B), cursor-ID imm {len(ids)} 件")
        for addr, v in ids:
            print(f"    {addr}: 0x{v:x} {IDC.get(v, '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
