#!/usr/bin/env python3
"""PY-59 (#1974): .pdata の関数ごとに逆アセンブルし、指定 VA を rip 相対で参照する命令を列挙する (実機不要)。

  python3 analysis/py59_refs.py <PE.bin> <target VA hex> [<target VA hex> ...]

線形走査ではなく関数単位で復号するため、関数間のデータ混じりによる同期ずれを避ける。
"""
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    targets = {int(x, 16) for x in sys.argv[2:]}
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    sec = next(s for s in pe.sections if s.Name.startswith(b".text"))
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for f in pe.DIRECTORY_ENTRY_EXCEPTION:
        b, e = f.struct.BeginAddress, f.struct.EndAddress
        if not (sec.VirtualAddress <= b < sec.VirtualAddress + sec.Misc_VirtualSize):
            continue
        code = data[sec.PointerToRawData + (b - sec.VirtualAddress):sec.PointerToRawData + (e - sec.VirtualAddress)]
        for ins in md.disasm(code, base + b):
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    ea = ins.address + ins.size + op.mem.disp
                    if ea in targets:
                        print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {ea:#x}")


if __name__ == "__main__":
    main()
