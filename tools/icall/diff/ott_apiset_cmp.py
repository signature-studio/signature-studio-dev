#!/usr/bin/env python3
"""OTT_vst2_win64.dll の security cookie と api-set 表 (32 × u64) を PE 直読みし、decode 結果を出す。

用法: python3 tools/icall/diff/ott_apiset_cmp.py <OTT_vst2_win64.dll>
出典: tools/icall/REPORT_APPENDIX_2225.md §2.3・§3 (#2225)。

各 VA (8 B) は次のどれかに分類し、セクション名・raw 範囲・virt 範囲と併せて表示する:
  raw           : 全 8 B が SizeOfRawData の範囲内 (ファイルの実バイト)
  一部 zero-fill : 先頭だけ raw 範囲内 (残りはファイル外・0 固定)
  zero-fill     : 全 8 B が raw 範囲外・virt 範囲内 (ファイル外・0 固定。読取りではない)
  セクション外   : virt 範囲のどのセクションにも入らない (0 固定。読取りではない)
zero-fill / セクション外 の entry は decode しない (実値が無いため)。
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
            return s
    return None


def read_qword(pe, base, va):
    s = locate(pe, base, va)
    if s is None:
        return None, "セクション外 (0 固定。読取りではない)", "セクション: なし"
    sec_va = base + s.VirtualAddress
    name = s.Name.rstrip(b"\0").decode(errors="replace")
    info = (f"セクション {name}: raw 0x{sec_va:x}-0x{sec_va + s.SizeOfRawData:x}, "
            f"virt 0x{sec_va:x}-0x{sec_va + s.Misc_VirtualSize:x}")
    off = va - sec_va
    raw_len = s.SizeOfRawData
    if off + 8 <= raw_len:
        value = struct.unpack_from("<Q", pe.__data__, s.PointerToRawData + off)[0]
        return value, "raw", info
    if off >= raw_len:
        return None, "zero-fill (ファイル外・0 固定。読取りではない)", info
    part = pe.__data__[s.PointerToRawData + off:s.PointerToRawData + raw_len]
    value = struct.unpack("<Q", part.ljust(8, b"\0"))[0]
    return value, "一部 zero-fill (後半はファイル外・0 固定)", info


def ror64(x, r):
    r &= 63
    return ((x >> r) | (x << (64 - r))) & MASK64 if r else x


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    cookie, ck_kind, ck_info = read_qword(pe, base, COOKIE_VA)
    if cookie is None or ck_kind != "raw":
        sys.exit(f"cookie VA 0x{COOKIE_VA:x} が raw 範囲にない ({ck_kind}): decode 不能")
    rot = cookie & 0x3F
    print(f"cookie VA 0x{COOKIE_VA:x} = 0x{cookie:x} (rot {rot}) [{ck_kind}] {ck_info}")
    for i in range(N_ENTRY):
        va = APISET_VA + 8 * i
        raw, kind, info = read_qword(pe, base, va)
        head = f"entry[{i:2d}] VA 0x{va:x} [{kind}] {info}"
        if raw is None or kind.startswith("一部"):
            print(head + " → decode 対象外")
            continue
        print(head + f" raw=0x{raw:016x} decoded=0x{ror64(raw ^ cookie, rot):016x}")


if __name__ == "__main__":
    main()
