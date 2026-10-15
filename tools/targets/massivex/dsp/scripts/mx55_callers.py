#!/usr/bin/env python3
"""MX-55 (#5030): 0x17b680 (scalar 読みの内部 float 関数) の呼出元を探す。

探索 (直接 E8/E9 は 0 件のため、間接経路だけを見る):
  1. .rdata 内で 0x17b680 のアドレスを指す 8 バイト slot を集め、所属 vtable と slot index を出す。
  2. 各 slot index の disp (index*8) を持つ `call qword ptr [reg + disp]` の機械語 (ff /2 disp32) を集める。
  3. 各 call の直前 (同一関数の窓・最大 40 命令) で xmm2 を書く命令を探す。
限界: 呼出元の rcx (this) の型は追わない。vtable slot の一致と xmm2 の書き込みで候補を絞るだけ。

usage: mx55_callers.py <pe> [target_rva_hex]
"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

CALL_RE = re.compile(rb'\xff([\x90\x91\x92\x93\x95\x96\x97])([\x00-\xff]{4})')


def main(pe_path, target_rva='0x17b680'):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    sec = {s.Name.rstrip(b'\0'): s for s in pe.sections}
    rd = sec[b'.rdata']
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    T = base + int(target_rva, 16)
    t_lo, t_hi = base + text.VirtualAddress, base + text.VirtualAddress + text.Misc_VirtualSize
    rd_lo = base + rd.VirtualAddress
    rd_hi = rd_lo + rd.Misc_VirtualSize

    def rq(va):
        return struct.unpack_from('<Q', data, rd.PointerToRawData + (va - rd_lo))[0]

    slots = []
    for va in range(rd_lo, rd_hi - 7, 8):
        if rq(va) != T:
            continue
        v = va
        while v - 8 >= rd_lo and t_lo <= rq(v - 8) < t_hi:
            v -= 8
        slots.append((va, v, (va - v) // 8))
    for va, v, idx in slots:
        print('slot %#x vtable %#x index %d disp %#x' % (va, v, idx, idx * 8))

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    blob = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    disps = {idx * 8 for _, _, idx in slots}
    sites = []
    for m in CALL_RE.finditer(blob):
        if int.from_bytes(m.group(2), 'little', signed=True) not in disps:
            continue
        h = m.start()
        lo = max(0, h - 96)
        insns = list(md.disasm(blob[lo:h + 16], t_lo + lo))
        if not any(i.address == t_lo + h for i in insns):
            continue
        sites.append((t_lo + h, insns))

    print('call [reg+disp] sites with a matching slot disp: %d' % len(sites))
    hit_xmm2 = 0
    for va, insns in sites:
        before = [i for i in insns if i.address < va]
        win = []
        for i in reversed(before):
            win.append(i)
            if i.mnemonic in ('ret', 'jmp', 'call') or len(win) >= 40:
                break
        writer = None
        for i in win:
            _, wr = i.regs_access()
            if any(md.reg_name(r) == 'xmm2' for r in wr):
                writer = i
                break
        if writer is not None:
            hit_xmm2 += 1
            print('  %#x xmm2 writer %#x %s %s' % (va, writer.address, writer.mnemonic, writer.op_str))
    print('sites with xmm2 written in the window: %d' % hit_xmm2)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
