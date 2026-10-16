#!/usr/bin/env python3
"""PLG-P0b-64 (#5663): CreatePlugInstance の Tag (第 2 引数) の供給元を機械語から逆向きに追う。

使い方:
  FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone 入り lib> python3 hs_tag_chain.py

出力は各段の関数先頭・直接呼出元・引数の由来。値が実行時のみで決まる箇所は「未確定」と表示する。
"""
import os
import struct
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
LOADER_CALL = 0x132C711   # lea rdx,[rip+0xaa] (UTF-16 "CreatePlugInstance") -> call 0x4235f0 -> call rax
GETPROC = 0x4235F0        # GetProcAddress 相当の wrapper
LOADER_FN = 0x132C680     # 0x132c711 を含む関数 (第 3 引数 r8 を [rbp+0x30] に保存)


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


def disasm(base, code, lo, hi):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    for i in md.disasm(code[lo - base:hi - base], lo):
        print('  %s %s %s' % (hex(i.address), i.mnemonic, i.op_str))


def main():
    base, code = load()
    print('[1] CreatePlugInstance 呼出し周辺 %s (loader fn %s の内側)' % (hex(LOADER_CALL), hex(LOADER_FN)))
    disasm(base, code, LOADER_CALL, LOADER_CALL + 0x30)
    print('    (rdx=[rbp+0x30] を CreatePlugInstance の Tag として call rax)')
    print('    loader fn 先頭:')
    disasm(base, code, LOADER_FN, LOADER_FN + 0x10)
    print('[2] loader fn の直接呼出元 (Tag = その rcx/r8)')
    for c in callers(base, code, LOADER_FN):
        print('  caller', hex(c))
        disasm(base, code, c - 0x10, c + 0x6)
    print('[3] Tag 元の関数 0x132ee00 の直接呼出元 (第 1 引数 rcx = Tag 候補)')
    for c in callers(base, code, 0x132EE00):
        print('  caller', hex(c))
        disasm(base, code, c - 0x18, c + 0x6)


if __name__ == '__main__':
    main()
