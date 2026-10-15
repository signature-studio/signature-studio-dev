#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、メモリオペランドの変位 (disp) が指定値の命令を列挙し、store / load / lea に分類する (PY-218 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disp_scan.py <disp(16進)>

例: pe_disp_scan.py 22fc は [reg+0x22fc] (grid のバイト配列の字段) を読む・書く命令を列挙する。
分類: 第 1 オペランドがそのメモリなら store (mov・add 等)、lea は lea、それ以外は load。RIP 相対 ([rip + disp]) は対象外。
線形走査は無効バイトで止まるため、1 命令ずつ進める (pe_xref.py と同じ方式)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    disp = int(sys.argv[1], 16)
    tag = f"+ 0x{disp:x}]"
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    data = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    start = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    counts = {"store": 0, "load": 0, "lea": 0}
    off = 0
    while off < len(data):
        got = list(md.disasm(data[off:off + 16], start + off, 1))
        if not got:
            off += 1
            continue
        ins = got[0]
        off += ins.size
        if tag not in ins.op_str or "[rip" in ins.op_str:
            continue
        first = ins.op_str.split(",")[0]
        if ins.mnemonic == "lea":
            kind = "lea"
        elif tag in first and ins.mnemonic not in ("cmp", "test"):
            kind = "store"
        else:
            kind = "load"
        counts[kind] += 1
        print(hex(ins.address), kind, ins.mnemonic, ins.op_str)
    print(f"disp={hex(disp)} store={counts['store']} load={counts['load']} lea={counts['lea']}")


if __name__ == "__main__":
    main()
