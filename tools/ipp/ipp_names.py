#!/usr/bin/env python3
"""FLEngine の ipp 名文字列表 (FPC UnicodeString リテラル連続) を列挙する。
   hdr: u16 codepage(1200) u16 elem(2) i32 refcnt(-1) i64 len ; data utf16 + NUL ; 8 byte 整列"""
import sys, struct, re, json
def walk(path, tag='dsp_ippv2.dylib'):
    b = open(path, 'rb').read()
    p = tag.encode('utf-16le')
    first = b.find(p)
    o = first - 24
    names = []
    while True:
        cp, el, _pad, rc, ln = struct.unpack_from('<HHIqq', b, o)
        if cp != 1200 or el != 2 or not (0 < ln < 80): break
        s = b[o+24:o+24+ln*2].decode('utf-16le')
        names.append(s)
        o += 24 + ln*2 + 2
        o = (o + 7) & ~7
    return names
if __name__ == '__main__':
    r = {}
    for s in ('x86_64', 'arm64'):
        n = walk(f'work/FLEngine.{s}'); r[s] = n
        print(s, len(n), n[:3], n[-3:])
    json.dump(r, open('work/flengine_ipp_names.json', 'w'), indent=0)
    a, x = r['arm64'], r['x86_64']
    print('same order/equal:', a == x, ' only in x:', len(set(x) - set(a)), ' only in a:', len(set(a) - set(x)))
