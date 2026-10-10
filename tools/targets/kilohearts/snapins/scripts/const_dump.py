#!/usr/bin/env python3
"""const_dump.py — pe_dis.py 出力 (.dis) 内の rip 相対参照の実値をダンプする (scenario 範囲決定用)。
usage: const_dump.py work/xxx_proc.dis   (pe_dis.py の '%x:\\tmn\\tops' 形式。次行 va から命令長を復元)
"""
import re
import struct
import sys

from pe_dis import pe, data, BASE

SEC = []
for s in pe.sections:
    SEC.append((BASE + s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.Name.rstrip(b'\0').decode(), s.PointerToRawData))


def rd(va, n):
    for lo, sz, nm, off in SEC:
        if lo <= va < lo + sz:
            o = off + va - lo
            return data[o:o + n]
    return None


def sec_of(va):
    for lo, sz, nm, off in SEC:
        if lo <= va < lo + sz:
            return nm
    return '?'


lines = []
for line in open(sys.argv[1]):
    m = re.match(r'^([0-9a-f]+):\t(.*)$', line.rstrip('\n'))
    if m:
        lines.append((int(m.group(1), 16), m.group(2)))

for i, (va, txt) in enumerate(lines):
    mm = re.search(r'\[rip \+ (0x[0-9a-f]+)\]', txt)
    if not mm or i + 1 >= len(lines):
        continue
    nxt = lines[i + 1][0]
    va_c = nxt + int(mm.group(1), 16)
    b = rd(va_c, 16)
    if not b:
        print('%x  %-46s -> %x (unreadable)' % (va, txt, va_c))
        continue
    f4 = struct.unpack('<4f', b[:16])
    f8 = struct.unpack('<2d', b[:16])
    print('%-12s %-46s -> %x %-8s u=%s f32=%s f64=%s' % ('%x' % va, txt, va_c, sec_of(va_c), b[:16].hex(),
                                                         ['%.9g' % x for x in f4], ['%.17g' % x for x in f8]))
