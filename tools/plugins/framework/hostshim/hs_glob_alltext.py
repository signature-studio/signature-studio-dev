#!/usr/bin/env python3
"""hs_glob_alltext.py — global 0x15e4790 / 0x141d6b8 への書込み・参照を全 PE ブロックの .text で探す (PLG-P0b-49 / #4444)。

hs_glob_writers.py は block00031 の .text だけを走査していた。本スクリプトは全 *_PE.bin の
全 .text 区間を走査し、次の 3 種を列挙する:
  * STORE: rip 相対で G (±0x40) を指すメモリ宛先の命令 (書込み候補)
  * REF:   rip 相対で G (±0x40) を指すその他の命令 (読み出し・lea)
  * ABS:   オペランドに G / 0x141d6b8 の絶対値を含む命令 (即値・絶対アドレス)

結果は REPORT_DISPATCHER_APPENDIX_4444.md §3 が解釈する。本スクリプトは出力を作るだけ。

使い方: FL_WIN64_DIR=<fl-win64 の展開先> python3 hs_glob_alltext.py
  (展開先は extracted/*_PE.bin を含むこと)
"""
import glob
import os
import re
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

G = 0x15e4790
P0 = 0x141d6b8
RIP_RE = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


def sweep(md, code, va):
    # 線形 sweep。skipdata で不正バイトを .byte として飛ばし、section 末尾まで流す
    # (capstone.disasm は既定では最初の不正バイトで止まる)。
    md.skipdata = True
    return md.disasm(code, va)


def main():
    d = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted')
    files = sorted(glob.glob(os.path.join(d, '*_PE.bin')))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    stores, refs, absh = [], [], []
    ntext = 0
    for f in files:
        pe = pefile.PE(f, fast_load=True)
        base = pe.OPTIONAL_HEADER.ImageBase
        name = os.path.basename(f)
        for s in pe.sections:
            if not s.Name.startswith(b'.text'):
                continue
            ntext += 1
            tva = base + s.VirtualAddress
            for ins in sweep(md, s.get_data(), tva):
                op = ins.op_str
                m = RIP_RE.search(op)
                if m:
                    disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                    t = ins.address + ins.size + disp
                    if abs(t - G) <= 0x40 or abs(t - P0) <= 0x40:
                        dst = op.split(',')[0].strip()
                        rec = (name, ins.address, t, ins.mnemonic, op)
                        if '[' in dst and ins.mnemonic not in ('cmp', 'test', 'lea'):
                            stores.append(rec)
                        else:
                            refs.append(rec)
                elif ('0x%x' % G) in op or ('0x%x' % P0) in op:
                    absh.append((name, ins.address, ins.mnemonic, op))
    print('text sections scanned: %d (PE blocks: %d)' % (ntext, len(files)))
    print('STORE (rip-rel, memory dst, within 0x40 of G/P0): %d' % len(stores))
    for r in stores:
        print('  %s 0x%x -> 0x%x  %s %s' % r)
    print('REF (rip-rel, other, within 0x40 of G/P0): %d' % len(refs))
    for r in refs:
        print('  %s 0x%x -> 0x%x  %s %s' % r)
    print('ABS (absolute operand equal to G/P0): %d' % len(absh))
    for r in absh:
        print('  %s 0x%x  %s %s' % r)
    return 0


if __name__ == '__main__':
    sys.exit(main())
