#!/usr/bin/env python3
"""hs_glob_bytes.py — global G=0x15e4790 / P0=0x141d6b8 の 32bit 即値・disp32 形式の出現を全 PE ブロックで数える (PLG-P0b-60 / #5547)。

hs_glob_alltext.py は rip 相対と絶対オペランドだけを見る。本スクリプトは、G / P0 の
リトルエンディアン 4 バイトが、どの PE ブロックのどのセクションに現れるかを生バイトで数える。
.text に現れた場合は、その位置を含む命令を線形逆アセンブルで特定する。
結果は REPORT_DISPATCHER_APPENDIX_4444.md が解釈する。

使い方: FL_WIN64_DIR=<fl-win64 の展開先> PYTHONPATH=<pefile,capstone> python3 hs_glob_bytes.py
  (展開先は extracted/*_PE.bin を含むこと)
"""
import glob
import os
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PATS = {'G': 0x15e4790, 'P0': 0x141d6b8}


def main():
    d = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted')
    files = sorted(glob.glob(os.path.join(d, '*_PE.bin')))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    hits = []
    for f in files:
        pe = pefile.PE(f, fast_load=True)
        base = pe.OPTIONAL_HEADER.ImageBase
        name = os.path.basename(f)
        for s in pe.sections:
            data = s.get_data()
            sname = s.Name.rstrip(b'\0').decode('latin1')
            for label, val in PATS.items():
                pat = struct.pack('<I', val)
                i = data.find(pat)
                while i != -1:
                    va = base + s.VirtualAddress + i
                    ins = None
                    if sname.startswith('.text'):
                        for x in md.disasm(data, base + s.VirtualAddress):
                            if x.address <= va < x.address + x.size:
                                ins = (x.address, x.mnemonic, x.op_str)
                                break
                    hits.append((name, sname, label, va, ins))
                    i = data.find(pat, i + 1)
    print('PE blocks: %d' % len(files))
    print('byte hits (G/P0, 4-byte LE): %d' % len(hits))
    for name, sname, label, va, ins in hits:
        if ins is None:
            print('  %s %s %s at 0x%x (non-text)' % (name, sname, label, va))
        else:
            print('  %s %s %s at 0x%x in insn 0x%x %s %s' % (name, sname, label, va, ins[0], ins[1], ins[2]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
