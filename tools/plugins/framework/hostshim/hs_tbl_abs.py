#!/usr/bin/env python3
"""PLG-P0b-67 (#5871): 関数表 TABLE_VA を絶対アドレスで指す命令の列挙。

hs_tbl_refs.py (rip 相対のみ) の補完。次の 3 形を見る:
  - メモリ disp が TABLE_VA 近傍 (base レジスタ無し、または任意の base): [reg*8 + disp32] など
  - 即値 (imm) が TABLE_VA 近傍: mov reg, imm32 / lea 系の即値
  - 生バイトの絶対 disp32 (SIB で base 無し) は capstone 側で拾えるので別走査しない

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tbl_abs.py [TABLE_VA] [WINDOW]
"""
import os
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OPT_ON
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')


def load():
    pe = pefile.PE(PE_PATH, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    return ib + text.VirtualAddress, text.get_data()


def main():
    table = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x12B0380
    win = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x8
    base, code = load()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    hits = []
    n = 0
    off = 0
    while off < len(code):
        got = list(md.disasm(code[off:off + 16], base + off, 1))
        if not got:
            off += 1
            continue
        i = got[0]
        n += 1
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base != X86_REG_RIP:
                if 0 <= op.mem.disp - table <= win or table - win <= op.mem.disp <= table:
                    hits.append((i.address, 'mem', i.mnemonic, i.op_str))
            if op.type == X86_OP_IMM and table <= (op.imm & 0xFFFFFFFF) <= table + win:
                hits.append((i.address, 'imm', i.mnemonic, i.op_str))
        off += i.size
    print('線形逆アセンブル %d 命令, table=%s, 窓 %s' % (n, hex(table), hex(win)))
    for a, kind, m, s in hits:
        print('  %s [%s]: %s %s' % (hex(a), kind, m, s))
    print('ヒット %d 件' % len(hits))


if __name__ == '__main__':
    main()
