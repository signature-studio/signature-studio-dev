#!/usr/bin/env python3
"""PE の delay import 記述子 (ImgDelayDescr) の IAT/INT 対応を列挙する (#3258)。

使い方: python3 tools/shared/oss/freetype/delay_int_map.py <block*_PE.bin>
出力: 記述子ごとの DLL 名・rvaIAT/rvaINT・dwTimeStamp と、各 IAT スロットの INT エントリ (名前 / 序数)。
i386 QuickFontCache (block24349) の 0x41065c (delay-load helper) は [ebp-0x44] に INT[idx] の
名前ポインタ (VA+2) か序数を入れ、GetProcAddress に渡す。よって本表の名前がそのまま lpProcName になる。
末尾に FT_/FTC_ 名の件数を出す (FT 名が delay 経路に載るかの判定)。
"""
import struct
import sys


def main(path):
    b = open(path, 'rb').read()
    pe = struct.unpack_from('<I', b, 0x3C)[0]
    assert b[pe:pe + 4] == b'PE\0\0', 'PE signature が無い'
    nsec = struct.unpack_from('<H', b, pe + 6)[0]
    optsz = struct.unpack_from('<H', b, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', b, opt)[0]
    assert magic == 0x10B, 'PE32 (i386) のみ対応'
    image_base = struct.unpack_from('<I', b, opt + 28)[0]
    secs = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        vs, va, rs, rp = struct.unpack_from('<IIII', b, o + 8)
        secs.append((va, max(vs, rs), rp))

    def r2o(rva):
        for va, sz, rp in secs:
            if va <= rva < va + sz:
                return rp + (rva - va)
        raise SystemExit('bad rva %#x' % rva)

    def cstr(o):
        return b[o:b.index(b'\0', o)].decode('latin1')

    dly_rva, dly_size = struct.unpack_from('<II', b, opt + 96 + 13 * 8)
    print('image_base=%#x delay_dir RVA=%#x size=%#x' % (image_base, dly_rva, dly_size))
    names = []
    ords = 0
    if dly_rva:
        o = r2o(dly_rva)
        for d in range(dly_size // 32):
            attr, dll_rva, hmod, iat, int_rva, bound, unload, stamp = struct.unpack_from('<8I', b, o + 32 * d)
            if not dll_rva:
                break
            assert attr & 1, 'VA ベースの delay 記述子 (grAttrs bit0 = 0) は未対応'
            dll = cstr(r2o(dll_rva))
            print('== desc[%d] pidd=VA %#x attrs=%#x DLL=%s rvaIAT=%#x rvaINT=%#x rvaBound=%#x stamp=%#x' % (
                d, image_base + dly_rva + 32 * d, attr, dll, iat, int_rva, bound, stamp))
            t = r2o(int_rva)
            k = 0
            while True:
                v = struct.unpack_from('<I', b, t + 4 * k)[0]
                if v == 0:
                    break
                slot = image_base + iat + 4 * k
                if v >> 31:
                    what = 'ORD %d' % (v & 0xFFFF)
                    ords += 1
                else:
                    nm = cstr(r2o(v) + 2)
                    what = 'NAME ' + nm
                    names.append(nm)
                print('  idx=%d IAT_VA=%#x INT=%#010x lpProcName=%s' % (k, slot, v, what))
                k += 1
            print('  count=%d' % k)
    ft = sorted(set(n for n in names if n.startswith(('FT_', 'FTC_'))))
    print('total NAME entries=%d ordinal entries=%d FT/FTC-named=%d %s' % (len(names), ords, len(ft), ft))


if __name__ == '__main__':
    main(sys.argv[1])
