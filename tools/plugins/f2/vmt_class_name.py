"""Delphi VMT のクラス名を PE 内の RTTI (TypeInfo) から読む (PLG-F3-44 / #4950)。

TypeInfo の並び: [kind=0x07 (tkClass)][名前 ShortString: len, bytes][ClassType dword][ParentInfo dword]...
ClassType dword が指定の VMT を指す TypeInfo を PE 全体から探し、その名前をクラス名とする。
ParentInfo が指す TypeInfo の名前も読み、継承関係を出す。

使い方:
  python vmt_class_name.py <PE> <VMT(16進)>
"""
import struct
import sys

import pefile


def main():
    path = sys.argv[1]
    vmt = int(sys.argv[2], 16)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()

    def va_to_off(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                return s.PointerToRawData + (rva - s.VirtualAddress)
        return None

    def off_to_va(off):
        for s in pe.sections:
            if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                return base + s.VirtualAddress + (off - s.PointerToRawData)
        return None

    def type_name(va):
        off = va_to_off(va)
        if off is None or data[off] != 0x07:
            return None
        ln = data[off + 1]
        raw = data[off + 2: off + 2 + ln]
        if ln == 0 or not all(0x20 <= c < 0x7F for c in raw):
            return None
        return raw.decode()

    pat = struct.pack("<I", vmt)
    idx = data.find(pat)
    found = 0
    while idx != -1:
        for n in range(1, 256):
            start = idx - n - 2
            if start < 0:
                break
            if data[start] == 0x07 and data[start + 1] == n:
                raw = data[start + 2: idx]
                if len(raw) == n and all(0x20 <= c < 0x7F for c in raw):
                    ti_va = off_to_va(start)
                    found += 1
                    print("TypeInfo at 0x%x: kind=tkClass name=%r ClassType=0x%x" % (ti_va, raw.decode(), vmt))
                    parent_off = idx + 4
                    parent = struct.unpack_from("<I", data, parent_off)[0]
                    print("ParentInfo=0x%x parent_name=%r" % (parent, type_name(parent)))
                break
        idx = data.find(pat, idx + 1)

    if not found:
        print("VMT 0x%x を ClassType に持つ tkClass の TypeInfo は見つからなかった" % vmt)


if __name__ == "__main__":
    main()
