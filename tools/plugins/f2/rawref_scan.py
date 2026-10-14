#!/usr/bin/env python3
"""capstone を使わない生バイト走査で、指定 VA への参照を数える (#2492 の検算)。

使い方: python3 rawref_scan.py <block_PE.bin> <VA> [<VA> ...]
.text の全バイト位置 p について disp32 = [p, p+4) を符号付きで読み、直後の即値長 k (0/1/2/4) を仮定して
飛び先 = p+4+k+disp32 が VA と一致するものを数える (rip 相対と rel32 の両方)。
4 バイト即値・絶対 disp32 は .text 内のバイト一致で数える。命令境界は使わないため、
capstone の disp_size 誤り (icall §4 D9) の影響を受けない。
"""
import struct
import sys

import pefile


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    lo = base + text.VirtualAddress
    code = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    vas = [int(s, 16) for s in argv[2:]]
    want = set(vas)
    rel = {}
    for p in range(len(code) - 3):
        t = lo + p + 4 + int.from_bytes(code[p:p + 4], "little", signed=True)
        for k in (0, 1, 2, 4):
            if t + k in want:
                rel.setdefault(t + k, []).append((hex(lo + p), k))
    for va_s, va in zip(argv[2:], vas):
        imm = [hex(lo + i) for i in range(len(code) - 3) if code[i:i + 4] == struct.pack("<I", va)]
        print(f"== {va_s}: rel (rip 相対・rel32, k=0/1/2/4) {len(rel.get(va, []))} 件 {rel.get(va, [])[:8]}")
        print(f"   .text 内の 4 バイト一致 {len(imm)} 件 {imm[:8]}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv)
