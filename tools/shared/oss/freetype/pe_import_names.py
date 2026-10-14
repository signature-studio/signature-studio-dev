#!/usr/bin/env python3
"""PE の import / delay-import 記述子の名前を列挙する (#1648)。

使い方: python3 tools/shared/oss/freetype/pe_import_names.py <block*_PE.bin>
出力: DLL ごとの名前 (序数は #N)、序数エントリ件数、FT 名の一覧。
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
    w = 8 if magic == 0x20B else 4
    dd_off = opt + (112 if w == 8 else 96)
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

    def names_of(ilt_rva):
        t = r2o(ilt_rva)
        out = []
        k = 0
        while True:
            v = struct.unpack_from('<Q' if w == 8 else '<I', b, t + w * k)[0]
            if v == 0:
                break
            if v >> (w * 8 - 1):
                out.append('#%d' % (v & 0xFFFF))
            else:
                out.append(cstr(r2o(v & ((1 << (w * 8 - 1)) - 1)) + 2))
            k += 1
        return out

    all_names = []
    imp_rva = struct.unpack_from('<I', b, dd_off + 8)[0]
    if imp_rva:
        o = r2o(imp_rva)
        while True:
            oft, _, _, nm, ft = struct.unpack_from('<IIIII', b, o)
            if not nm and not ft:
                break
            names = names_of(oft or ft)
            print('IMPORT', cstr(r2o(nm)), len(names))
            all_names += names
            o += 20
    dly_rva = struct.unpack_from('<I', b, dd_off + 13 * 8)[0]
    if dly_rva:
        o = r2o(dly_rva)
        while True:
            attr, dll_rva, _, _, int_rva = struct.unpack_from('<5I', b, o)
            if not dll_rva:
                break
            names = names_of(int_rva)
            print('DELAY', cstr(r2o(dll_rva)), len(names))
            all_names += names
            o += 32
    ft = sorted(set(n for n in all_names if n.startswith('FT')))
    ords = sum(1 for n in all_names if n.startswith('#'))
    print('total names', len(all_names), 'ordinal entries', ords, 'FT-named', ft)


if __name__ == '__main__':
    main(sys.argv[1])
