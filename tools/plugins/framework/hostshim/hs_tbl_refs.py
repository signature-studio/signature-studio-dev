#!/usr/bin/env python3
"""PLG-P0b-67 (#5871): 関数表 TABLE_VA を指す命令の列挙 (rip 相対の実オペランド)。

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tbl_refs.py [TABLE_VA]

.text を線形逆アセンブルし、rip 相対メモリオペランドの実効アドレス (次命令の VA + disp) が
TABLE_VA の近傍 (既定 ±0x100) に入る命令を出す。生バイト走査は誤検出 (命令境界外) が多いため使わない。
線形走査はデコードずれを含みうるので、結果は候補として扱い、呼出し箇所は逆アセンブルで確認する。
"""
import os
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OPT_ON
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
WINDOW = 0x100


def load():
    pe = pefile.PE(PE_PATH, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    return ib + text.VirtualAddress, text.get_data()


def main():
    table = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x12B0380
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
            if op.type != X86_OP_MEM or op.mem.base != X86_REG_RIP:
                continue
            ea = i.address + i.size + op.mem.disp
            if abs(ea - table) <= WINDOW:
                hits.append((i.address, ea, i.mnemonic, i.op_str))
        off += i.size
    print('線形逆アセンブル %d 命令, table=%s, 窓 ±%s' % (n, hex(table), hex(WINDOW)))
    for a, ea, m, s in hits:
        print('  %s: %s %s  -> %s' % (hex(a), m, s, hex(ea)))
    print('ヒット %d 件' % len(hits))


if __name__ == '__main__':
    main()
