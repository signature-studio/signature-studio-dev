#!/usr/bin/env python3
"""PE の .pdata から icall_rewrite.py 用の関数範囲 (CSV "0xA-0xB"・B は末尾 byte) を標準出力へ出す (#2565)。

fw_prep.py の F.ranges (Fruity Balance の全関数) と同じ規約: CHAININFO 以外の .pdata 項目で、
生バイト長が一致するものだけを取る。  python3 mk_franges.py block18983_PE.bin > F.ranges
"""
import struct, sys, pefile


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    fs = sorted({(b, e) for b, e, u in (struct.unpack_from('<III', pdata, 12 * k) for k in range(len(pdata) // 12)) if b and not u & 1})
    code = {s.VirtualAddress: s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Characteristics & 0x20000000}
    out = []
    for b, e in fs:
        raw = next((c[b - va:e - va] for va, c in code.items() if va <= b < va + len(c)), b'')
        if len(raw) != e - b or not raw:
            continue
        out.append('0x%x-0x%x' % (base + b, base + e - 1))
    print(','.join(out))


if __name__ == '__main__':
    main()
