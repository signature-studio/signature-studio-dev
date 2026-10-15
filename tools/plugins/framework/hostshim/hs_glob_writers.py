#!/usr/bin/env python3
"""hs_glob_writers.py — global 0x15e4790 (Dispatcher 応答 gate の連鎖の先頭) の書込み元を PE 全体で探す (PLG-P0b-49 / #4444)。

確認項目:
  * 各 PE ブロックに 0x15e4790 / 0x141d6b8 を指す qword が含まれるか (データ域のポインタ)
  * .text 内で 0x15e4790 の近傍 (±0x40) に rip 相対の mov 書込みがあるか
  * block00031_PE.bin の 0x15e4790 → *G → *(*G) の PE 内の初期値
結果は REPORT_DISPATCHER_APPENDIX_4444.md が解釈する。本スクリプトは出力を作るだけ。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_glob_writers.py
  (展開先は fl-win64.tar.zst の extracted/*_PE.bin を含むこと)
"""
import glob
import os
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

G = 0x15e4790
P0 = 0x141d6b8
MAIN_PE = 'block00031_PE.bin'
RIP_RE = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


def main():
    d = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted')
    files = sorted(glob.glob(os.path.join(d, '*_PE.bin')))
    print('PE blocks: %d' % len(files))
    for f in files:
        raw = open(f, 'rb').read()
        for t in (G, P0):
            i = raw.find(struct.pack('<Q', t))
            if i != -1:
                print('qword 0x%x in %s @ file+0x%x' % (t, os.path.basename(f), i))

    pe = pefile.PE(os.path.join(d, MAIN_PE), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()

    def q(va):
        return struct.unpack('<Q', img[va - base:va - base + 8])[0]

    p = q(G)
    print('G=0x%x (section %s) *G=0x%x *(*G)=0x%x' % (
        G, [s.Name.rstrip(b'\0').decode() for s in pe.sections
            if s.VirtualAddress + base <= G < s.VirtualAddress + base + s.Misc_VirtualSize],
        p, q(p)))

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    tva = base + text.VirtualAddress
    near = []
    for ins in md.disasm(text.get_data(), tva):
        m = RIP_RE.search(ins.op_str)
        if not m:
            continue
        disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
        g = ins.address + ins.size + disp
        if abs(g - G) <= 0x40 and ins.mnemonic == 'mov' and ins.op_str.split(',')[0].strip().endswith(']'):
            near.append((ins.address, g, ins.op_str))
    print('rip-global mov stores within 0x40 of G in .text: %d' % len(near))
    for a, g, op in near:
        print('  0x%x -> 0x%x  mov %s' % (a, g, op))


if __name__ == '__main__':
    sys.exit(main())
