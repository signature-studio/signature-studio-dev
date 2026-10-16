#!/usr/bin/env python3
"""hs_init_callers.py — global 0x15e4790 の連鎖の初期化関数 (0x976a90) と作成関数 (0x976b60) への PE 内の呼出し・参照を数える (PLG-P0b-62 / #5626)。

確認項目:
  * 全 .text* の直接 call / jmp で 0x976a90・0x976b60 を指すもの
  * 全 PE ブロックのデータ域で、0x976a90 を VA (0x400000 基準・0x140000000 基準) として持つ qword

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<pefile,capstone> python3 hs_init_callers.py
  (展開先は fl-win64.tar.zst の extracted/*_PE.bin を含むこと)
"""
import glob
import os
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

TARGETS = {0x976A90: 'init_fn', 0x976B60: 'create_fn'}
MAIN_PE = 'block00031_PE.bin'


def sweep(md, code, va):
    # 線形 sweep。skipdata で不正バイトを .byte として飛ばし、section 末尾まで流す
    # (capstone.disasm は既定では最初の不正バイトで止まる)。
    md.skipdata = True
    return md.disasm(code, va)


def main():
    d = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted')
    pe = pefile.PE(os.path.join(d, MAIN_PE), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    hits = []
    for s in pe.sections:
        if not s.Name.startswith(b'.text'):
            continue
        n = 0
        for ins in sweep(md, s.get_data(), base + s.VirtualAddress):
            n += 1
            if ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
                t = int(ins.op_str, 16)
                if t in TARGETS:
                    hits.append((ins.address, TARGETS[t], ins.mnemonic))
        print('section %s: insn %d' % (s.Name.rstrip(b'\0').decode(), n))
    # 対照: E8/E9 の総当たり (境界を検証しない候補)。線形 sweep の取りこぼし確認用
    for s in pe.sections:
        if not s.Name.startswith(b'.text'):
            continue
        code = s.get_data()
        tva = base + s.VirtualAddress
        for i in range(len(code) - 4):
            if code[i] in (0xE8, 0xE9):
                rel = struct.unpack_from('<i', code, i + 1)[0]
                if tva + i + 5 + rel in TARGETS:
                    print('  brute E8/E9 candidate 0x%x %s' % (tva + i, TARGETS[tva + i + 5 + rel]))
    print('direct call/jmp to init/create (linear sweep): %d' % len(hits))
    for a, name, m in hits:
        print('  0x%x %s %s' % (a, m, name))

    files = sorted(glob.glob(os.path.join(d, '*_PE.bin')))
    print('PE blocks: %d' % len(files))
    for va in TARGETS:
        for f in files:
            raw = open(f, 'rb').read()
            for t in (va, base + va):
                i = raw.find(struct.pack('<Q', t))
                while i != -1:
                    print('qword 0x%x in %s @ file+0x%x' % (t, os.path.basename(f), i))
                    i = raw.find(struct.pack('<Q', t), i + 1)


if __name__ == '__main__':
    sys.exit(main())
