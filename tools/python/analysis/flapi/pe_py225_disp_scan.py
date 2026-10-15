#!/usr/bin/env python3
"""grid 構造体の +0x22fc (件数付き byte 配列の pointer) を読み書きする命令を PE 全 .text の線形走査で列挙する (PY-225 #3651)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py225_disp_scan.py [disp(16進, 既定 22fc)]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
出力: 指定 disp を含む命令の一覧 (番号・VA・命令)。store (mov [reg+disp], ...) と load は分けて数える。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def sweep(raw, pe):
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            for ins in md.disasm(data[off:off + 16], start + off, 1):
                yield ins
                off += ins.size
                break
            else:
                off += 1


def main():
    disp = sys.argv[1].lower() if len(sys.argv) > 1 else "22fc"
    needle = "+ 0x%s]" % disp
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    stores, loads, lea = [], [], []
    for ins in sweep(raw, pe):
        t = ins.op_str
        if needle not in t:
            continue
        if ins.mnemonic == "lea":
            lea.append((ins.address, t))
        elif ins.mnemonic == "mov" and t.split(",")[0].endswith("]"):
            stores.append((ins.address, t))
        else:
            loads.append((ins.address, ins.mnemonic, t))
    print("disp 0x%s: store %d 件 / lea %d 件 / その他 %d 件" % (disp, len(stores), len(lea), len(loads)))
    print("[store]")
    for a, t in stores:
        print("  %s  mov %s" % (hex(a), t))
    print("[lea]")
    for a, t in lea:
        print("  %s  lea %s" % (hex(a), t))
    print("[other]")
    for a, m, t in loads:
        print("  %s  %s %s" % (hex(a), m, t))


if __name__ == "__main__":
    main()
