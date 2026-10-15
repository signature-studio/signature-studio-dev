#!/usr/bin/env python3
"""reloc_lifted_4727.py: 判定保留区間内の .text HIGHLOW reloc 1 本ずつを、lift 出力 (ott_lifted.c・lift_meta.json) に照らして分類する (PLG-G2-56 #4727)。

  python3 reloc_lifted_4727.py <PE> <lift 出力 dir> <区間先頭 VA hex> <区間終端 VA hex>

分類 (先に当てはまったもの):
  lifted-insn-start  : reloc 位置が lift 済み命令の先頭
  lifted-insn-inside : reloc 位置が lift 済み命令の途中 (jmp [reg*4+base] の disp32 など)
  jt-table           : reloc 位置が lift_meta の jt_ranges に入る
  NOT-LIFTED         : 上のどれでもない (lift されていない位置)
"""
import json, re, struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from collections import Counter


def main():
    pef, out = sys.argv[1], sys.argv[2]
    lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
    pe = pefile.PE(pef)
    IMG = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    src = open(out + '/ott_lifted.c').read()
    lifted = {int(m.group(1), 16) for m in re.finditer(r'/\* ([0-9a-f]+): ', src)}
    jt = json.load(open(out + '/lift_meta.json'))['jt_ranges']
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    span = set()
    for va in lifted:
        ins = next(md.disasm(img[va - IMG:va - IMG + 16], va, 1))
        span.update(range(va, va + ins.size))
    kinds = []
    for b in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in b.entries:
            va = IMG + e.rva
            if e.type != 3 or not (lo <= va < hi):
                continue
            v = struct.unpack_from('<I', img, e.rva)[0]
            if va in lifted:
                k = 'lifted-insn-start'
            elif va in span:
                k = 'lifted-insn-inside'
            elif any(s <= va < s + sz for s, sz in jt):
                k = 'jt-table'
            else:
                k = 'NOT-LIFTED'
            kinds.append(k)
            print('0x%x val=0x%08x %s' % (va, v, k))
    print('[reloc] %d 本 %s' % (len(kinds), dict(Counter(kinds))))


if __name__ == '__main__':
    main()
