#!/usr/bin/env python3
"""VEX comis/ucomis 命令の直後に flag を読む機械語命令 (jcc / setcc / cmovcc) を数える ([PLG-F3-14] #1774 の実測)。
usage: vex_comis_consumers.py <PE.bin> <ranges.txt> [v]   (v: 1 命令ごとに出す)
出力: 命令 '->' 最初の flag 消費命令 の件数 (例 vcomisd->je)。 IR 側の消費 (flag 名の参照の有無) は REPORT_APPENDIX_1774.md §7c。
"""
import re, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
ranges = [tuple(int(x, 16) for x in r.split('-')) for r in open(sys.argv[2]).read().strip().split(',')]
FLAGRD = re.compile(r'^(j(?!mp)\w+|set\w+|cmov\w+|adc|sbb)$')
VEXCOMIS = ('vcomisd', 'vucomisd', 'vcomiss', 'vucomiss')


def read(va, n):
    for s in pe.sections:
        sva = base + s.VirtualAddress
        if sva <= va < sva + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = va - sva
            return s.get_data()[off:off + n]
    return b''


cnt = {}
for a, e in ranges:
    for ins in md.disasm(read(a, e - a + 1), a):
        if ins.mnemonic not in VEXCOMIS:
            continue
        cons = ''
        nxt = read(ins.address + ins.size, 40)
        for j in md.disasm(nxt, ins.address + ins.size):
            if j.mnemonic.startswith(('mov', 'vmov')) or j.mnemonic in ('nop', 'lea'):
                continue
            if FLAGRD.match(j.mnemonic):
                cons = j.mnemonic
            break
        k = '%s->%s' % (ins.mnemonic, cons or 'none')
        cnt[k] = cnt.get(k, 0) + 1
        if len(sys.argv) > 3:
            print('%x' % ins.address, ins.mnemonic, ins.op_str, '->', cons or 'none')
for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
    print(v, k)
