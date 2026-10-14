#!/usr/bin/env python3
"""PY-54 (#1912): .pdata (RUNTIME_FUNCTION) で VA を含む関数を求め、その全体を逆アセンブルする (実機不要)。

  python3 analysis/py54_func.py <PE.bin> <VA hex>

線形スイープと違い、関数の開始 VA を .pdata から取るので命令境界がずれない。
"""
import struct
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    va = int(sys.argv[2], 16)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    pdata = next(s for s in pe.sections if s.Name.startswith(b".pdata"))
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    raw = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
    rva = va - base
    best = None
    for i in range(0, len(raw) - 11, 12):
        b, e, _ = struct.unpack_from("<III", raw, i)
        if b <= rva < e:
            best = (b, e)
            break
    if best is None:
        print("no pdata entry")
        return
    b, e = best
    print(f"== function VA {base + b:#x} .. {base + e:#x} (size {e - b:#x}) ==")
    code = data[text.PointerToRawData + (b - text.VirtualAddress):text.PointerToRawData + (e - text.VirtualAddress)]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for ins in md.disasm(code, base + b):
        mark = " <==" if ins.address <= va < ins.address + ins.size else ""
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}{mark}")


if __name__ == "__main__":
    main()
