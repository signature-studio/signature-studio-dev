"""関数ポインタ表 (RVA 0x19c7e0, 81 組 = 162 要素) の全要素を観測用スタブへ差し替えた複製を作る (#3257 / T-SH-55)。
スタブは `jmp [IAT]` (kernel32 の指定 API への tail jump) で、呼出し元の戻り番地がそのまま API に見える。
relay trace の `Call KERNEL32.<API>() ret=...` から、表を読む関数の呼出し箇所を得られる。
usage: table_stub.py <src PE> <dst PE> <kernel32 API 名> <スタブ RVA (hex, 0 埋め領域)>
"""
import struct
import sys

TABLE_RVA, TABLE_PAIRS = 0x19C7E0, 81
IMAGE_BASE = 0x400000
src, dst, api, stub_s = sys.argv[1:5]
stub = int(stub_s, 16)

d = bytearray(open(src, "rb").read())
pe = struct.unpack_from("<I", d, 0x3C)[0]
opt = pe + 24
optsz = struct.unpack_from("<H", d, pe + 20)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
secs = []
for i in range(nsec):
    s = opt + optsz + i * 40
    vsz, va, rsz, rp = struct.unpack_from("<IIII", d, s + 8)
    secs.append((va, max(vsz, rsz), rp))


def r2o(rva):
    for va, sz, rp in secs:
        if va <= rva < va + sz:
            return rp + rva - va
    raise SystemExit(f"rva {rva:#x} not in any section")


def cstr(rva):
    o = r2o(rva)
    return d[o:d.index(b"\0", o)].decode(errors="replace")


def iat_slot(name):
    o = r2o(struct.unpack_from("<I", d, opt + 112 + 8)[0])  # import directory
    while True:
        oft, _, _, nm, ft = struct.unpack_from("<IIIII", d, o)
        if nm == 0:
            break
        if cstr(nm).lower() == "kernel32.dll":
            k = 0
            ilt = oft or ft
            while True:
                v = struct.unpack_from("<Q", d, r2o(ilt) + 8 * k)[0]
                if v == 0:
                    break
                if not v >> 63 and cstr(v + 2) == name:
                    return ft + 8 * k
                k += 1
        o += 20
    raise SystemExit(f"kernel32 import {name} not found")


slot = iat_slot(api)
o = r2o(stub)
if any(d[o:o + 6]):
    raise SystemExit(f"stub area at {stub:#x} is not zero")
d[o:o + 6] = b"\xff\x25" + struct.pack("<i", slot - (stub + 6))  # jmp qword ptr [rip+disp]
for k in range(2 * TABLE_PAIRS):
    struct.pack_into("<Q", d, r2o(TABLE_RVA) + 8 * k, IMAGE_BASE + stub)
open(dst, "wb").write(d)
print(f"stub {stub:#x}: jmp [{slot:#x}] ({api}); table {2 * TABLE_PAIRS} pointers -> {IMAGE_BASE + stub:#x}")
