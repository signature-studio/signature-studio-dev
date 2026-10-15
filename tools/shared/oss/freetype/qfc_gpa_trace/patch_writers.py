#!/usr/bin/env python3
# #3369 / T-SH-72: 登録簿 [0x5d0c90] の書込み命令 2 箇所の先頭バイトを int3 (0xCC) に置き換えた複製を作る。
# P は到達の確認用 (VEH が同じ命令をエミュレートして通過させる。表は writers_probe.c の SITES と一致させる)。
# 置換前に命令のバイト列を検査し、一致しなければ失敗する (fail-closed)。writers_probe.c の VEH が
# 同じ意味をエミュレートする。素材本体は変更しない。
# usage: patch_writers.py SRC_PE DST_PE
import struct
import sys

SITES = [
    ("W1", 0xF48B, bytes([0x49, 0x89, 0x55, 0x10]), "mov [r13+0x10],rdx"),
    ("W2", 0xFCF5, bytes([0xF3, 0x48, 0xA5]), "rep movsq"),
    ("P", 0xFB80, bytes([0x57]), "push rdi (0x40fb80 入口)"),
    ("P", 0xFB91, bytes([0xE8]), "call 0x40f8b0"),
    ("P", 0xFB96, bytes([0xE8]), "call 0x40faa0"),
    ("P", 0xFBB0, bytes([0xE8]), "call 0x406d90"),
    ("P", 0xFBCF, bytes([0xE8]), "call 0x40fa40"),
    ("P", 0xFBF9, bytes([0xFF, 0xD3]), "call rbx"),
    ("P", 0xFC2B, bytes([0xE8]), "call 0x409410"),
    ("P", 0xFC48, bytes([0xE8]), "call 0x40f2f0"),
    ("P", 0xFAD8, bytes([0xE8]), "call 0x406d00 (40faa0 内)"),
    ("P", 0xFAFB, bytes([0xE8]), "call 0x406d10 (40faa0 内)"),
    ("P", 0xFB14, bytes([0xE8]), "call 0x410f20 (40faa0 内)"),
    ("P", 0xFB33, bytes([0xE8]), "call 0x406d10 (40fb33)"),
    ("P", 0xFACD, bytes([0xFF, 0x15]), "call [rip+..] (40facd)"),
    ("P", 0xFB56, bytes([0xE8]), "call 0x406fb0 (40fb56)"),
]

src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, "rb").read())
pe = struct.unpack_from("<I", d, 0x3C)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
optsz = struct.unpack_from("<H", d, pe + 20)[0]
text_va, text_rp = None, None
for i in range(nsec):
    s = pe + 24 + optsz + i * 40
    if d[s : s + 8].rstrip(b"\0") == b".text":
        _, va, _, rp = struct.unpack_from("<IIII", d, s + 8)
        text_va, text_rp = va, rp
assert text_va is not None, ".text not found"
for name, rva, expect, what in SITES:
    o = text_rp + rva - text_va
    got = bytes(d[o : o + len(expect)])
    if got != expect:
        raise SystemExit(f"{name} {rva:#x} ({what}): bytes {got.hex()} != {expect.hex()}")
    d[o] = 0xCC
    print(f"{name}: RVA {rva:#x} file off {o:#x} {what} -> int3 (orig {expect.hex()})")
open(dst, "wb").write(d)
