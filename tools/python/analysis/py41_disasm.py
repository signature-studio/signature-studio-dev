#!/usr/bin/env python3
"""PY-41 (#1554): FLEngine PE の指定 VA を逆アセンブルする (実機不要)。

  python3 analysis/py41_disasm.py <PE.bin> <VA hex> [<VA hex> ...]

出力は関数ごとに、次の ret/int3 までの命令列と、call 先 VA を表示する。
PE は fl-win64 素材の extracted/block00031_PE.bin を使う (work/ に展開して渡す)。
"""
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    vas = [int(v, 16) for v in sys.argv[2:]]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for va in vas:
        r = va - base - text.VirtualAddress
        off = text.PointerToRawData + r
        print(f"== fn {va:#x} ==")
        for ins in md.disasm(data[off:off + 0x800], va):
            print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
            if ins.mnemonic == "ret" or (ins.mnemonic == "int3"):
                break
        print()


if __name__ == "__main__":
    main()
