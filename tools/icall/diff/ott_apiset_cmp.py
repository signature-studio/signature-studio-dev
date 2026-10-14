#!/usr/bin/env python3
"""OTT_vst2_win64.dll の security cookie と api-set 表 (32 × u64) を PE 直読みし、decode 結果を出す。

用法: python3 tools/icall/diff/ott_apiset_cmp.py <OTT_vst2_win64.dll>
出典: tools/icall/REPORT_APPENDIX_2225.md §2.3・§3 (#2225)。

各 VA の値は次のどちらかで出力する:
  raw       : PE ファイル上の生バイト (SizeOfRawData の範囲内)
  zero-fill : セクションの仮想領域のうち raw 範囲の外 (ファイル外・0 固定。実値ではない)
表が zero-fill 域にある場合、その entry は実値ではなく 0 として扱われる。
"""
import struct
import sys

import pefile

COOKIE_VA = 0x180260CE0
APISET_VA = 0x18026C9F0
N_ENTRY = 32
MASK64 = (1 << 64) - 1


def locate(pe, base, va):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s, rva - s.VirtualAddress
    return None, None


def read_va(pe, base, va, size):
    s, off = locate(pe, base, va)
    if s is None:
        return bytes(size), "outside (セクション外・0 固定)", None
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    n = max(0, min(size, s.SizeOfRawData - off))
    out = bytearray(size)
    if n:
        start = s.PointerToRawData + off
        out[:n] = pe.__data__[start:start + n]
    if n == size:
        kind = "raw"
    elif n == 0:
        kind = "zero-fill (ファイル外・0 固定)"
    else:
        kind = "一部 zero-fill"
    return bytes(out), kind, (name, s)


def ror64(x, r):
    r &= 63
    return ((x >> r) | (x << (64 - r))) & MASK64 if r else x


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    cookie_b, cookie_kind, _ = read_va(pe, base, COOKIE_VA, 8)
    cookie = struct.unpack("<Q", cookie_b)[0]
    rot = cookie & 0x3F
    print(f"cookie VA 0x{COOKIE_VA:x} = 0x{cookie:x} (rot {rot}) [{cookie_kind}]")
    table, kind, info = read_va(pe, base, APISET_VA, 8 * N_ENTRY)
    if info is not None:
        name, s = info
        raw_end = base + s.VirtualAddress + s.SizeOfRawData
        virt_end = base + s.VirtualAddress + s.Misc_VirtualSize
        print(f"section {name}: raw end 0x{raw_end:x}, virt end 0x{virt_end:x}")
    print(f"api-set 表 0x{APISET_VA:x}: 表全体 [{kind}]")
    raw_nonzero = 0
    for i in range(N_ENTRY):
        raw = struct.unpack_from("<Q", table, 8 * i)[0]
        if kind == "raw":
            raw_nonzero += raw != 0
        dec = ror64(raw ^ cookie, rot)
        print(f"entry[{i:2d}] raw=0x{raw:016x} decoded=0x{dec:016x}")
    if kind == "raw":
        print(f"api-set 表 0x{APISET_VA:x}: entry {N_ENTRY}, raw 由来の非ゼロ {raw_nonzero}/{N_ENTRY}")
    else:
        print(f"api-set 表 0x{APISET_VA:x}: entry {N_ENTRY}, 実値 (raw) なし。全 entry は {kind} で 0 扱い")


if __name__ == "__main__":
    main()
