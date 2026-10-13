#!/usr/bin/env python3
"""vt_slots.py <pe> <vtable-va-hex>... — 各 vtable の先頭から「.text を指す qword」が続く限りの全 slot 先 VA を `--icall VA` で列挙する (FA-8)。
slot 数を固定せず走査するため、未解決 icall の取りこぼし (FA-8 実測: slot 12 以降の 0x1803de640/0x1803de670/0x180460b50) を防ぐ。"""
import sys, struct, pefile
pe = pefile.PE(sys.argv[1]); b = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
lo, hi = b + text.VirtualAddress, b + text.VirtualAddress + text.Misc_VirtualSize
rd = [s for s in pe.sections if s.Name.startswith(b'.rdata')][0]; d = rd.get_data(); va0 = b + rd.VirtualAddress
out = set()
for a in sys.argv[2:]:
    o = int(a, 16) - va0
    while o + 8 <= len(d):
        t = struct.unpack_from('<Q', d, o)[0]
        if not (lo <= t < hi): break
        out.add(t); o += 8
print(' '.join('--icall %x' % t for t in sorted(out)))
