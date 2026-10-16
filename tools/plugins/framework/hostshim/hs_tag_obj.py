#!/usr/bin/env python3
"""PLG-P0b-64 (#5663): 段 5 の rcx の由来のうち 0x10041f0 の戻り値を機械語から分類する。

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tag_obj.py

出力: 0x10041f0 の直接呼出元の数と、関数本体・直下の初期化関数 (0x1003be0・0x1003d40) の逆アセンブル。
"""
import os
import struct
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
FACTORY = 0x10041F0
SUB = [(0x1003BE0, 0x28), (0x1003D40, 0x60)]


def load():
    pe = pefile.PE(PE_PATH, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    return ib + text.VirtualAddress, text.get_data()


def callers(base, code, target):
    out = []
    for k in range(len(code) - 5):
        if code[k] == 0xE8 and base + k + 5 + struct.unpack_from('<i', code, k + 1)[0] == target:
            out.append(base + k)
    return out


def dis(base, code, addr, n):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    off = addr - base
    for i in md.disasm(code[off:off + n], addr):
        print(f'  {i.address:#x} {i.mnemonic} {i.op_str}')


def main():
    base, code = load()
    cs = callers(base, code, FACTORY)
    print(f'callers of {FACTORY:#x}: {len(cs)} 件')
    for c in cs:
        print(f'  {c:#x}')
    print(f'{FACTORY:#x} (factory 本体):')
    dis(base, code, FACTORY, 0x40)
    for a, n in SUB:
        print(f'{a:#x}:')
        dis(base, code, a, n)


if __name__ == '__main__':
    main()
