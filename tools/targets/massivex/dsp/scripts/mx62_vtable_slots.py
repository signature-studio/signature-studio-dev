"""MX-62 (#5657): vtable slot 30/32 の中身と、関数 VA を値として持つ 8 バイト位置を列挙する。

usage: python3 mx62_vtable_slots.py <Massive X.vst3>

出力: 2 つの vtable の slot 30・32 の値 (RVA)、0x17b460・0x17b680・0x17a4b0 を
値として持つ .rdata/.data の 8 バイト位置 (ファイル全体の走査)。
"""
import struct
import sys

import pefile

VTABLES = {"vt_IInstrument": 0x41836A8, "vt_main": 0x3976038}
SLOTS = (30, 32)
TARGETS = (0x17B460, 0x17B680, 0x17A4B0)


def read_rva(pe, rva, n=8):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            off = rva - s.VirtualAddress + s.PointerToRawData
            return pe.__data__[off:off + n]
    raise ValueError(hex(rva))


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    for name, vt in VTABLES.items():
        print(f"{name} VA={base + vt:#x}")
        for k in SLOTS:
            val = struct.unpack("<Q", read_rva(pe, vt + 8 * k))[0] - base
            print(f"  slot {k} -> RVA {val:#x}")
    data = pe.__data__
    for t in TARGETS:
        pat = struct.pack("<Q", base + t)
        hits = []
        i = data.find(pat)
        while i >= 0:
            hits.append(i)
            i = data.find(pat, i + 1)
        print(f"RVA {t:#x}: 8-byte 値の一致 {len(hits)} 件")
        for h in hits:
            for s in pe.sections:
                if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData:
                    rva = s.VirtualAddress + (h - s.PointerToRawData)
                    print(f"  {s.Name.rstrip(b' ' + bytes(1)).decode()} RVA {rva:#x}")


if __name__ == "__main__":
    main()
