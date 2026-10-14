#!/usr/bin/env python3
"""OTT_vst2_win64.dll の security cookie と api-set 表 (32 × u64) を PE 直読みし、decode 結果を出す。

用法: python3 tools/icall/diff/ott_apiset_cmp.py <OTT_vst2_win64.dll>
出典: tools/icall/REPORT_APPENDIX_2225.md §2.3・§3 (#2225)。
VA が .data の raw 範囲の外 (zero-fill 域) にある場合は 0 として読む。
"""
import struct
import sys

import pefile

COOKIE_VA = 0x180260CE0
APISET_VA = 0x18026C9F0
N_ENTRY = 32
MASK64 = (1 << 64) - 1


def read_va(pe, base, va, size):
    rva = va - base
    for s in pe.sections:
        start = s.VirtualAddress
        span = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if start <= rva < start + span:
            off = rva - start
            out = bytearray(size)
            if off < s.SizeOfRawData:
                n = min(size, s.SizeOfRawData - off)
                raw = pe.__data__[s.PointerToRawData + off:s.PointerToRawData + off + n]
                out[:len(raw)] = raw
            return bytes(out)
    return bytes(size)


def ror64(x, r):
    r &= 63
    return ((x >> r) | (x << (64 - r))) & MASK64 if r else x


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    cookie = struct.unpack("<Q", read_va(pe, base, COOKIE_VA, 8))[0]
    rot = cookie & 0x3F
    print(f"cookie VA 0x{COOKIE_VA:x} = 0x{cookie:x} (rot {rot})")
    table = read_va(pe, base, APISET_VA, 8 * N_ENTRY)
    nonzero = 0
    for i in range(N_ENTRY):
        raw = struct.unpack_from("<Q", table, 8 * i)[0]
        nonzero += raw != 0
        dec = ror64(raw ^ cookie, rot)
        print(f"entry[{i:2d}] raw=0x{raw:016x} decoded=0x{dec:016x}")
    print(f"api-set 表 0x{APISET_VA:x}: entry {N_ENTRY}, raw 非ゼロ {nonzero}/{N_ENTRY}")


if __name__ == "__main__":
    main()
