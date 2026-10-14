#!/usr/bin/env python3
# MX-3b U1: 全 COL (x64 Complete Object Locator) を走査し、基底一覧に指定型名を持つ具象クラスを列挙する。
# COL 判定: signature(+0)==1 かつ pSelf(+20)==自身の RVA (偽陽性を強く抑える)。
# 各 COL について 主 vtable VA = (COL を指す 8 byte ポインタの位置) + 8 を出す。pdata 非依存。
# usage: mx_iap_vtable.py <pe> <base_type_name> [...]
#   例: mx_iap_vtable.py work/extracted/VST3/Massive\ X.vst3 '.?AVIAudioProcessor@Vst@Steinberg@@'
import sys, struct
import pefile


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    IB = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    rdata = [s for s in pe.sections if s.Name.rstrip(b'\0') in (b'.rdata', b'.data')]
    secs = [(IB + s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections]
    wanted = sys.argv[2:]

    def rd(va, n):
        for base, vsz in secs:
            if base <= va and va + n <= base + vsz:
                return img[va - IB:va - IB + n]
        return None

    def u32(va):
        b = rd(va, 4)
        return struct.unpack('<I', b)[0] if b else None

    def cstr(va, n=200):
        b = rd(va, n) or b''
        return b.split(b'\0')[0].decode('latin1')

    # 全 COL を列挙
    cols = []
    for s in rdata:
        base = IB + s.VirtualAddress
        raw = img[s.VirtualAddress:s.VirtualAddress + s.Misc_VirtualSize]
        for off in range(0, len(raw) - 24, 4):
            if struct.unpack_from('<I', raw, off)[0] != 1:
                continue
            col_va = base + off
            if u32(col_va + 20) != col_va - IB:
                continue
            cols.append(col_va)
    print('COL candidates (x64 sig+pSelf 一致): %d' % len(cols))

    # COL -> (型名, 基底名一覧)
    hits = {}
    for col_va in cols:
        r_td, r_cd = u32(col_va + 12), u32(col_va + 16)
        if r_td is None or r_cd is None or rd(IB + r_cd, 16) is None:
            continue
        td, cd = IB + r_td, IB + r_cd
        tname = cstr(td + 0x10)
        numbase = u32(cd + 8)
        if numbase is None or numbase == 0 or numbase > 64 or u32(cd + 12) is None:
            continue
        arr = IB + u32(cd + 12)
        bases, ok = [], True
        for i in range(numbase):
            r_bcd = u32(arr + 4 * i) if rd(arr + 4 * i, 4) else None
            if r_bcd is None or r_bcd == 0 or rd(IB + r_bcd, 4) is None:
                ok = False
                break
            r_btd = u32(IB + r_bcd)
            if r_btd is None or rd(IB + r_btd + 0x10, 1) is None:
                ok = False
                break
            bases.append(cstr(IB + r_btd + 0x10))
        if not ok:
            continue
        for w in wanted:
            if w in bases:
                hits.setdefault(w, []).append((col_va, tname, bases))

    for w in wanted:
        lst = hits.get(w, [])
        print('base %s: COL %d 件' % (w, len(lst)))
        for col_va, tname, bases in lst:
            # COL を指す 8 byte ポインタ (vtable[-1]) を探す。vtable = 位置 + 8
            pat = struct.pack('<Q', IB + (col_va - IB))
            vts = []
            start = 0
            while True:
                i = img.find(pat, start)
                if i < 0:
                    break
                vts.append(IB + i + 8)
                start = i + 1
            for vt in vts:
                print('  vtable 0x%x  COL=0x%x  type=%s  numBase=%d' % (vt, col_va, tname, len(bases)))


if __name__ == '__main__':
    main()
