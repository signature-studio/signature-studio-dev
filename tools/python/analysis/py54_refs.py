#!/usr/bin/env python3
"""PY-54 (#1912): 指定 VA を指す RIP 相対メモリ参照を .text 全体から列挙する (実機不要)。

  python3 analysis/py54_refs.py <PE.bin> <VA hex> [<VA hex> ...]

PE は fl-win64 素材の extracted/block00031_PE.bin を使う (work/ に展開して渡す)。
各参照に読み (R) / 書き (W: 第 1 オペランドがメモリ) の別を付ける。
capstone の線形スイープは不正バイトで同期を失うため、失敗位置の次の 1 byte から再走査する。
結果は命令の取り逃がし・データ領域の誤デコードを含みうるので、判定は REPORT の注記に従う。
"""
import sys

import capstone
import pefile


def main():
    path = sys.argv[1]
    targets = {int(v, 16) for v in sys.argv[2:]}
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    code = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    va0 = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    pos = 0
    while pos < len(code):
        advanced = False
        for ins in md.disasm(code[pos:pos + 0x10000], va0 + pos):
            pos = ins.address - va0 + ins.size
            advanced = True
            for op in ins.operands:
                if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
                    continue
                ea = ins.address + ins.size + op.mem.disp
                if ea in targets:
                    rw = "W" if ins.operands[0].type == capstone.x86.X86_OP_MEM and op is ins.operands[0] else "R"
                    print(f"{rw} {ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {ea:#x}")
        if not advanced:
            pos += 1


if __name__ == "__main__":
    main()
