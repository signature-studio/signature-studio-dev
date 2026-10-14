#!/usr/bin/env python3
"""PY-59 (#1974): .pdata (RUNTIME_FUNCTION) から VA を含む関数の範囲を求め、その全命令を出す (実機不要)。

  python3 analysis/py59_func.py <PE.bin> <VA hex> [dump]

引数なしで範囲だけ出す。dump を付けると関数内の全命令を逆アセンブルする。
"""
import sys

import capstone
import pefile


def find_func(pe, va_rva):
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    best = None
    for f in pe.DIRECTORY_ENTRY_EXCEPTION:
        b, e = f.struct.BeginAddress, f.struct.EndAddress
        if b <= va_rva < e:
            if best is None or (e - b) < (best[1] - best[0]):
                best = (b, e)
    return best


def main():
    path = sys.argv[1]
    va = int(sys.argv[2], 16)
    dump = len(sys.argv) > 3 and sys.argv[3] == "dump"
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rva = va - base
    rng = find_func(pe, rva)
    if rng is None:
        raise SystemExit("no RUNTIME_FUNCTION covers this VA")
    b, e = rng
    print(f"func {base + b:#x}..{base + e:#x} (size {e - b:#x})")
    if not dump:
        return
    sec = next(s for s in pe.sections if s.VirtualAddress <= b < s.VirtualAddress + s.Misc_VirtualSize)
    data = open(path, "rb").read()
    raw = data[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]
    code = raw[b - sec.VirtualAddress:e - sec.VirtualAddress]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for ins in md.disasm(code, base + b):
        mark = ">>" if ins.address == va else "  "
        print(f"{mark} {ins.address:#x}: {ins.mnemonic} {ins.op_str}")


if __name__ == "__main__":
    main()
