#!/usr/bin/env python3
# MX-3b U1: vtable 先頭 VA の RTTI (MSVC x64) を読む。vtable[-1] = COL (Complete Object Locator)。
# COL.pTypeDescriptor の名前と、COL.pClassDescriptor の基底クラス配列の名前を出す。
# COL.offset は、この vtable が属する最終オブジェクト内での this 位置 (負値は 0 とみなす)。
# pdata 非依存。usage: mx_vtable_rtti.py <pe> <vtable_va_hex> [...]
import sys, struct
import pefile


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    IB = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    secs = [(IB + s.VirtualAddress, s.Misc_VirtualSize, s) for s in pe.sections]

    def rd(va, n):
        for base, vsz, _ in secs:
            if base <= va and va + n <= base + vsz:
                return data[va - IB:va - IB + n]
        return None

    def u32(va):
        b = rd(va, 4)
        return struct.unpack('<I', b)[0] if b else None

    def u64(va):
        b = rd(va, 8)
        return struct.unpack('<Q', b)[0] if b else None

    def cstr(va, n=160):
        b = rd(va, n) or b''
        return b.split(b'\0')[0].decode('latin1')

    for a in sys.argv[2:]:
        vt = int(a, 16)
        col = u64(vt - 8)
        if not col:
            print('0x%x: no COL' % vt)
            continue
        # COL (x64): signature u32, offset u32, cdOffset u32, pTypeDescriptor i32 (RVA),
        # pClassDescriptor i32 (RVA), pSelf i32 (RVA)
        sig, off, cdoff = u32(col), u32(col + 4), u32(col + 8)
        tdrva, cdrva = u32(col + 12), u32(col + 16)
        td = IB + tdrva
        name = cstr(td + 0x10)  # TypeDescriptor: pVFTable(8) spare(8) name[]
        cd = IB + cdrva
        print('vtable 0x%x  COL=0x%x sig=%d offset=0x%x cdOffset=0x%x cd=0x%x' % (vt, col, sig, off, cdoff, cd))
        print('  type = %s' % name)
        # RTTIClassHierarchyDescriptor: signature(+0) attributes(+4) numBaseClasses(+8) pBaseClassArray(+12, RVA)
        numbase = u32(cd + 8)
        arr = IB + u32(cd + 12)
        for i in range(numbase):
            # RTTIBaseClassDescriptor: pTypeDescriptor(+0, RVA) numContainedBases(+4) mdisp(+8) pdisp(+12) vdisp(+16) attributes(+20)
            bcd = IB + u32(arr + 4 * i)
            btd = IB + u32(bcd)
            print('  base[%d] = %s  (numContained=%d mdisp=%d pdisp=%d vdisp=%d attr=%d)' % (
                i, cstr(btd + 0x10),
                u32(bcd + 4),
                struct.unpack('<i', rd(bcd + 8, 4))[0],
                struct.unpack('<i', rd(bcd + 12, 4))[0],
                struct.unpack('<i', rd(bcd + 16, 4))[0],
                u32(bcd + 20)))


if __name__ == '__main__':
    main()
