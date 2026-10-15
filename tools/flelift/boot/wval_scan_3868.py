#!/usr/bin/env python3
"""wval_scan_3868.py — #3868 (FLE-17) 受入条件 4: 0x6bbc20 を指す参照の静的走査 (逆アセンブル版)。

REPORT_APPENDIX_3771 §D の「4 byte 即値は PE 全体で 0 件」は imm32 のみの走査。rip 相対 lea
(0x6bc1a8: lea rax,[rip-0x58f]) は即値ではないため、その走査では拾えない。本スクリプトは
.text を capstone で逆アセンブルし、rip 相対の memory operand と即値 (imm32/imm64) の両方で
TARGET を指す命令を数える。PE は FL_WIN64_DIR 配下の block00031_PE.bin (boot と同じ入力)。

使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 boot/wval_scan_3868.py [--target 0x6bbc20]
"""
import argparse
import os
import struct
import sys

import capstone
import pefile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', default='0x6bbc20')
    ap.add_argument('--pe', default=None)
    a = ap.parse_args()
    target = int(a.target, 16)
    pe_path = a.pe or os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
    pe = pefile.PE(pe_path)
    img = pe.get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits_rip, hits_imm, n_ins = [], [], 0
    for s in pe.sections:
        name = s.Name.rstrip(b'\0').decode(errors='replace')
        if not name.startswith('.text'):
            continue
        va0 = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress
        sz = s.Misc_VirtualSize or s.SizeOfRawData
        data = img[s.VirtualAddress: s.VirtualAddress + sz]
        off = 0
        while off < len(data):
            ins = next(md.disasm(data[off:off + 16], va0 + off), None)
            if ins is None:
                off += 1
                continue
            off += ins.size
            n_ins += 1
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    if ins.address + ins.size + op.mem.disp == target:
                        hits_rip.append((ins.address, ins.mnemonic, ins.op_str))
                if op.type == capstone.x86.X86_OP_IMM and (op.imm & 0xffffffff) == target:
                    hits_imm.append((ins.address, ins.mnemonic, ins.op_str))
    print('insns=%d rip_rel_hits=%d imm_hits=%d' % (n_ins, len(hits_rip), len(hits_imm)))
    for h in hits_rip:
        print('rip  0x%x %s %s' % h)
    for h in hits_imm:
        print('imm  0x%x %s %s' % h)


if __name__ == '__main__':
    sys.exit(main())
