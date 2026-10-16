#!/usr/bin/env python3
"""PLG-P0b-67 (#5871): 関数表 [TABLE_LO, TABLE_HI] を指す命令の全 .text 走査。

hs_tbl_refs.py (線形逆アセンブル) は命令境界のずれを含みうるので、ここでは .text の全バイト位置
(p = 0 .. len-1) から 1 命令ずつ復号し、次の 3 形式を数える:
  - rip 相対メモリオペランドの実効アドレスが表の範囲に入る
  - 絶対 disp (base なし・index の有無を問わない) のメモリオペランドの disp が表の範囲に入る
  - 即値・絶対 disp の 4 バイト値が表の範囲に入る (復号できた命令のみ)
表の範囲外の値の検出は行わない。

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tbl_scan.py
"""
import os
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP, X86_REG_INVALID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
TABLE_LO = 0x12B02E0
TABLE_HI = 0x12B0468


def main():
    pe = pefile.PE(PE_PATH, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    base = ib + text.VirtualAddress
    with open(PE_PATH, 'rb') as f:
        f.seek(text.PointerToRawData)
        code = f.read(text.SizeOfRawData)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    rip_hits, abs_hits, imm_hits = [], [], []
    decoded = 0
    for p in range(len(code)):
        for i in md.disasm(code[p:p + 16], base + p, 1):
            decoded += 1
            for op in i.operands:
                if op.type == X86_OP_MEM:
                    if op.mem.base == X86_REG_RIP:
                        ea = i.address + i.size + op.mem.disp
                        if TABLE_LO <= ea <= TABLE_HI:
                            rip_hits.append((i.address, i.mnemonic, i.op_str))
                    elif op.mem.base == X86_REG_INVALID:
                        if TABLE_LO <= op.mem.disp <= TABLE_HI:
                            abs_hits.append((i.address, i.mnemonic, i.op_str))
                elif op.type == X86_OP_IMM and TABLE_LO <= (op.imm & 0xFFFFFFFF) <= TABLE_HI:
                    imm_hits.append((i.address, i.mnemonic, i.op_str))
            break
    print('復号できた開始位置 %d (.text %d バイト)' % (decoded, len(code)))
    print('表 %s..%s' % (hex(TABLE_LO), hex(TABLE_HI)))
    print('rip 相対で指す命令: %d 件' % len(rip_hits))
    for a, m, s in rip_hits[:20]:
        print('  %s %s %s' % (hex(a), m, s))
    print('絶対 disp + index で指す命令: %d 件' % len(abs_hits))
    for a, m, s in abs_hits[:20]:
        print('  %s %s %s' % (hex(a), m, s))
    print('即値が表の範囲に入る命令: %d 件' % len(imm_hits))
    for a, m, s in imm_hits[:20]:
        print('  %s %s %s' % (hex(a), m, s))
    with open(PE_PATH, 'rb') as f:
        pe_bytes = f.read()
    for name, va in [('表の基底', TABLE_LO), ('表の終端', TABLE_HI), ('0x12ba440 (表の先頭要素)', 0x12BA440)]:
        for width, fmt in [(8, '<Q'), (4, '<I')]:
            pat = struct.pack(fmt, va)
            n = pe_bytes.count(pat)
            print('PE 全体のバイト列 %s %s (%d バイト): %d 件' % (name, hex(va), width, n))


if __name__ == '__main__':
    main()
