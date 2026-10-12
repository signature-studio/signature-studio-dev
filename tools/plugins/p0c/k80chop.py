#!/usr/bin/env python3
"""k80chop.py — kernel 機械語の fldcw RC=chop 区間を抽出し f80_lower --chop-ranges の
仕様文字列を生成する (CAB-196 / REPORT §10)。

  python3 k80chop.py [VAs]        (既定: work/k80_ranges.txt の全 kernel)

x87 control word の RC = bits 10-11 (00=nearest, 01=down, 10=up, 11=chop)。
fldcw が chop を設定したアドレスから, 次の nearest 復帰 fldcw までを chop 区間と
する。区間を持たない kernel は対象外 (全 op nearest)。

出力例: 5dfbe0:5dfc0a-5dfc7c,5dfdb0:5dfded-5dfe40
"""
import json
import os
import struct
import sys

import pefile
import capstone
from capstone import Cs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
PE = os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')


def load(path):
    pe = pefile.PE(data=open(path, 'rb').read(), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    F = {}
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    for k in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * k)
        if b and not u & 1:
            F[base + b] = base + e
    return pe, base, F


def va_rd16(pe, base, va):
    """full VA 空間で u16 を読む (F/section VA とも full VA で統一)。"""
    for s in pe.sections:
        va0 = base + s.VirtualAddress
        if va0 <= va < va0 + max(s.Misc_VirtualSize, s.SizeOfRawData):
            data = s.get_data()
            off = va - va0
            if off + 2 <= len(data):
                return int.from_bytes(data[off:off + 2], 'little')
    return None


def scan(md, td, tva, va, fend, pe, base):
    ranges = []
    start = None
    for i in md.disasm(td[va - tva:fend - tva], va):
        if i.mnemonic != 'fldcw' or not i.operands:
            continue
        op = i.operands[0]
        if op.type != capstone.x86.X86_OP_MEM:
            continue
        if op.mem.base != capstone.x86.X86_REG_RIP:
            continue
        cw = va_rd16(pe, base, i.address + i.size + op.mem.disp)
        if cw is None:
            continue
        if (cw >> 10) & 3 == 3:                       # RC=chop 設定
            if start is None:
                start = i.address
        elif start is not None:                       # nearest 復帰
            ranges.append((start, i.address))
            start = None
    if start is not None:
        ranges.append((start, fend))
    return ranges


def main():
    vas = [a.lstrip('0x') for a in sys.argv[1:]] or None
    if not vas:
        rp = os.path.join(HERE, 'work', 'k80_ranges.txt')
        vas = []
        for part in open(rp).read().strip().split(','):
            if '-' in part:
                vas.append(part.split('-', 1)[0].lstrip('0x'))
    pe, base, F = load(PE)
    tva = base + [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0].VirtualAddress
    td = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0].get_data()
    md = Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out, detail = [], {}
    for va in vas:
        v = int(va, 16)
        if v not in F:
            continue
        rng = scan(md, td, tva, v, F[v], pe, base)
        if rng:
            detail['%x' % int(va, 16)] = ['%x-%x' % r for r in rng]
            out.append('%s:%s' % (va, ','.join('%x-%x' % r for r in rng)))
    spec = ','.join(out)
    print(spec)
    json.dump(detail, open(os.path.join(HERE, 'work', 'k80chop.json'), 'w'), indent=1)
    print('[k80chop] %d kernel with chop -> work/k80chop.json' % len(detail), file=sys.stderr)


if __name__ == '__main__':
    main()
