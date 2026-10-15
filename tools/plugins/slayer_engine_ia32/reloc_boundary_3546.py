#!/usr/bin/env python3
"""reloc_boundary_3546.py: 判定保留区間内の .text reloc 位置が命令境界か、線形掃引で確かめる (PLG-G2-28 #3546)。

  python3 reloc_boundary_3546.py <PE> <区間先頭 VA hex> <区間終端 VA hex>

出力: 区間内の HIGHLOW reloc を 1 本ずつ、(1) 線形掃引 (CS_MODE_32、区間先頭から) で命令の先頭に当たるか、
(2) 当たる場合はその命令、当たらない場合は当たる命令の先頭、(3) reloc の値 を表示する。
線形掃引は区間先頭から 1 本の流れで読むため、途中で不正命令があれば以降は参考値になる (表示する)。
"""
import struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def main():
    pe = pefile.PE(sys.argv[1])
    lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    T0 = IMG + text.VirtualAddress
    TS = text.Misc_VirtualSize
    img = pe.get_memory_mapped_image()
    code = img[text.VirtualAddress + (lo - T0):text.VirtualAddress + (hi - T0)]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    starts = {}
    for ins in md.disasm(code, lo):
        starts[ins.address] = (ins.mnemonic, ins.op_str, ins.size)
    print('[sweep] 区間 0x%x〜0x%x (%d B)、線形掃引の命令 %d 個' % (lo, hi, hi - lo, len(starts)))
    n = 0
    inside_insn = 0
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            if e.type != 3:
                continue
            va = IMG + e.rva
            if not (lo <= va < hi):
                continue
            n += 1
            v = struct.unpack_from('<I', img, e.rva)[0]
            if va in starts:
                m, o, _ = starts[va]
                how = '命令先頭: %s %s' % (m, o)
            else:
                head = max((a for a in starts if a < va), default=None)
                m, o, sz = starts[head]
                how = '命令の途中 (先頭 0x%x: %s %s)' % (head, m, o)
                inside_insn += 1
            print('0x%x  val=0x%08x  %s' % (va, v, how))
    print('[reloc] 区間内の HIGHLOW %d 本、うち命令の途中 %d 本' % (n, inside_insn))


if __name__ == '__main__':
    main()
