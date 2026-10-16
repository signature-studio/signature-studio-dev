#!/usr/bin/env python3
"""PLG-P0b-64 (#5663): hs_tag_chain.py の段 5 (0x132ee00 の rcx) の追跡。

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tag_rcx.py

段 5 の 5 件の呼出元の rcx 由来と、0x132f3f0 の呼出元の rcx 由来を出す。
関数先頭は push rbp の直前 (0xcc/0xc3/0x90) を境界とした近似。
"""
import os
import struct
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
TARGET_TAG_FN = 0x132EE00
CALLERS_TAG_FN = [0x10F2372, 0x10F24B2, 0x10F2CC4, 0x10F2D90, 0x132F43F]
CALLER_OF_0x132F3F0 = 0x12BA5EC
MD = Cs(CS_ARCH_X86, CS_MODE_64)


def load():
    pe = pefile.PE(PE_PATH, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    return ib + text.VirtualAddress, text.get_data()


def callers(base, code, target):
    out = []
    for k in range(len(code) - 5):
        if code[k] == 0xE8:
            rel = struct.unpack_from('<i', code, k + 1)[0]
            if base + k + 5 + rel == target:
                out.append(base + k)
    return out


def fn_start(base, code, addr):
    off = addr - base
    for k in range(off, off - 0x4000, -1):
        if code[k] == 0x55 and code[k - 1] in (0xCC, 0xC3, 0x90, 0xC2):
            return base + k
    return None


def rcx_sources(base, code, call_addr):
    start = fn_start(base, code, call_addr)
    if start is None:
        return None, []
    insns = list(MD.disasm(code[start - base:call_addr + 6 - base], start))
    writes = [i for i in insns if i.mnemonic in ('mov', 'lea') and i.op_str.startswith('rcx, ')]
    return start, writes[-3:]


def main():
    base, code = load()
    print('[A] 0x132ee00 (Tag 元) の直接呼出元 5 件の rcx 由来 (呼出し直前の rcx 設定)')
    for c in CALLERS_TAG_FN:
        if c not in callers(base, code, TARGET_TAG_FN):
            print('  %s: 直接 E8 呼出しとして検出されない' % hex(c))
            continue
        start, writes = rcx_sources(base, code, c)
        print('  caller %s (関数先頭 %s)' % (hex(c), hex(start) if start else '不明'))
        for i in writes:
            print('    %s %s %s' % (hex(i.address), i.mnemonic, i.op_str))
    print('[B] 0x132f3f0 の呼出元 %s の rcx' % hex(CALLER_OF_0x132F3F0))
    start, writes = rcx_sources(base, code, CALLER_OF_0x132F3F0)
    print('  関数先頭 %s' % (hex(start) if start else '不明'))
    for i in writes:
        print('    %s %s %s' % (hex(i.address), i.mnemonic, i.op_str))


if __name__ == '__main__':
    main()
