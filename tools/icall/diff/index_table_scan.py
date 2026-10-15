#!/usr/bin/env python3
# index_table_scan.py — ICALL-85 (#3089): 添字表 0x1810df738 の dword 値と、5 slot に届く添字 n の照合。
#   用法: python3 tools/icall/diff/index_table_scan.py <SlateCore.core_64 (PE)>
#   式: 180703b7c・180703913 の添字 rcx は movsxd で表の dword を読む (表の位置は [base+rax*4+0x10df738])。
#       表の読出し位置 p = 0x1810df738 + 4a (a は符号付き)。p の dword 値 v が n (5 slot に届く添字) と一致すれば届き得る。
#   出力: section ごとに、一致した dword の位置 p・値 v・添字 a = (p - 0x1810df738) / 4 と、対応する命令。
#   表の全長は決めない。全 section を走査して一致の有無を見る (届かないことの確認用)。
import struct
import sys

IMAGE_BASE = 0x180000000
TABLE = 0x1810DF738
SLOTS = [0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910]
SITES = [("180703b7c", "[rbx+rcx*8+0x125c7e8]", 0x125C7E8),
         ("180703913", "[r8+rcx*8+0x125c7b8]", 0x125C7B8)]


def reach(disp):
    out = []
    for s in SLOTS:
        d = s - IMAGE_BASE - disp
        if d % 8 == 0:
            out.append(d // 8)
    return out


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    base = pe + 24 + optsz
    out = []
    for i in range(nsec):
        o = base + 40 * i
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsz, va, rawsz, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, IMAGE_BASE + va, min(vsz, rawsz), rawptr))
    return out


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    targets = {}
    for name, disp_site, disp in [(s[0], s[1], s[2]) for s in SITES]:
        for n in reach(disp):
            targets.setdefault(n, []).append(name)
    for n in sorted(targets):
        print(f"届く添字 n = {n:,} (site {','.join(targets[n])})")
    print(f"表 {TABLE:#x} を含む section と走査範囲 (file 上の dword):")
    total = 0
    for name, va, size, raw in sections(data):
        if raw == 0 or size == 0:
            continue
        cnt = size // 4
        vals = struct.unpack_from(f"<{cnt}i", data, raw)
        hits = [(i, v) for i, v in enumerate(vals) if v in targets]
        total += cnt
        print(f"  {name:8s} {va:#x}-{va + size:#x} dwords={cnt:,} 一致={len(hits)} a∈[{(va - TABLE) // 4:,}, {(va + size - TABLE) // 4:,})")
        for i, v in hits[:20]:
            p = va + 4 * i
            a = (p - TABLE) // 4
            print(f"      p={p:#x} v={v:,} a={a:,} site={','.join(targets[v])}")
        if len(hits) > 20:
            print(f"      ... 残り {len(hits) - 20:,} 件")
    print(f"走査 dword 合計 {total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
