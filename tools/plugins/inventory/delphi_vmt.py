#!/usr/bin/env python3
"""Delphi x64 の VMT (クラス) をダンプする補助。
使い方: delphi_vmt.py <PE> <VMT_VA> [nslots]
Delphi x64 VMT ヘッダ(VMT ポインタからの負オフセット): -88 SelfPtr, -80 IntfTable, -72 AutoTable,
-64 InitTable, -56 TypeInfo, -48 FieldTable, -40 MethodTable, -32 DynamicTable, -24 ClassName,
-16 InstanceSize, -8 Parent。VMT[0..] は仮想メソッド (TObject の 8 個が先頭)。
"""
import sys, struct
import pefile


class Img:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        self.pe = pefile.PE(data=self.d)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase

    def rd(self, va, n):
        o = self.pe.get_offset_from_rva(va - self.base)
        return self.d[o:o + n]

    def q(self, va):
        return struct.unpack('<Q', self.rd(va, 8))[0]

    def d32(self, va):
        return struct.unpack('<I', self.rd(va, 4))[0]

    def pstr(self, va):
        b = self.rd(va, 256)
        return b[1:1 + b[0]].decode('latin1')

    def in_img(self, va):
        return self.base <= va < self.base + self.pe.OPTIONAL_HEADER.SizeOfImage


def dump(img, vmt, n=40):
    print('VMT %x' % vmt)
    cn = img.q(vmt - 24)
    print('  ClassName: %s' % (img.pstr(cn) if img.in_img(cn) else hex(cn)))
    print('  InstanceSize: %d' % img.q(vmt - 16))
    par = img.q(vmt - 8)
    if par and img.in_img(par):
        pv = img.q(par)
        print('  Parent VMT: %x (%s)' % (pv, img.pstr(img.q(pv - 24))))
    for i in range(n):
        v = img.q(vmt + 8 * i)
        if not img.in_img(v):
            print('  [%02d] +%03x = %x (non-image; end)' % (i, 8 * i, v))
            break
        print('  [%02d] +%03x = %x' % (i, 8 * i, v))


if __name__ == '__main__':
    img = Img(sys.argv[1])
    dump(img, int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 40)
