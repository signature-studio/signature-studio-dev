#!/usr/bin/env python3
"""MX-60 (#5498) 追補: vtable index 30 (disp 0xf0) を呼ぶ間接 call の列挙と、0x17b460 の入口。

受入 1・2 のための材料。0x17b460 は vt_IInstrument (0x1841836a8) の index 30 からのみ参照される。
この script は .text 内の `call qword ptr [reg+0xf0]` を全て出し、呼出し直前 14 命令の窓を示す。
あわせて 0x17b460 の入口 14 命令を出す (rcx → rbx の複写の確認)。

usage: mx60c_slot30.py <pe>
"""
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM

ENTRY_RVA = 0x17B460
DISP = 0xF0
WINDOW = 14


def main(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = base + text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    blob = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    ex = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    ex_sec = [s for s in pe.sections if s.VirtualAddress <= ex.VirtualAddress < s.VirtualAddress + s.Misc_VirtualSize][0]
    ex_off = ex.VirtualAddress - ex_sec.VirtualAddress + ex_sec.PointerToRawData
    funcs = sorted((base + struct.unpack_from('<II', data, ex_off + k * 12)[0],
                    base + struct.unpack_from('<II', data, ex_off + k * 12)[1]) for k in range(ex.Size // 12))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    sites = []
    for fs, fe in funcs:
        if not (t_lo <= fs < t_hi):
            continue
        ins = list(md.disasm(blob[fs - t_lo:fe - t_lo], fs))
        for n, i in enumerate(ins):
            if i.mnemonic != 'call' or not i.operands:
                continue
            op = i.operands[0]
            if op.type == X86_OP_MEM and op.mem.disp == DISP and op.mem.base != 0:
                sites.append((fs - base, n, ins))
    print('== call qword ptr [reg+0xf0] (index 30) の箇所: %d 件 ==' % len(sites))
    for fn, n, ins in sites:
        lo = max(0, n - WINDOW)
        print('-- in fn %#x at %#x' % (fn, ins[n].address - base))
        for j in ins[lo:n + 1]:
            print('   %#x  %s %s' % (j.address - base, j.mnemonic, j.op_str))
    entry = [s for s in funcs if s[0] == base + ENTRY_RVA]
    print('== 0x17b460 の入口 ==')
    if entry:
        fs, fe = entry[0]
        for j in list(md.disasm(blob[fs - t_lo:fs - t_lo + 64], fs))[:WINDOW]:
            print('   %#x  %s %s' % (j.address - base, j.mnemonic, j.op_str))
    print('== 0x17b460 を値として含む非実行セクションの 8 バイト位置 (vtable 候補) ==')
    target = base + ENTRY_RVA
    for s in pe.sections:
        if s.Characteristics & 0x20000000:
            continue
        raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        name = s.Name.rstrip(b'\0').decode(errors='replace')
        for off in range(0, len(raw) - 7, 8):
            if struct.unpack_from('<Q', raw, off)[0] == target:
                print('   %s RVA %#x' % (name, s.VirtualAddress + off))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
