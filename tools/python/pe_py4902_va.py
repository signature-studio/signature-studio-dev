#!/usr/bin/env python3
"""PY-4902 (#5287): block00031_PE.bin の VA を逆アセンブル・型記述子を読む。

使い方:
  FL_WIN64_DIR=<展開先> python3 pe_py4902_va.py dis <VA> [命令数]
  FL_WIN64_DIR=<展開先> python3 pe_py4902_va.py desc <VA>
展開先は `extracted/block00031_PE.bin` を含むディレクトリ。
"""
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, Cs

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DATA = open(PE, "rb").read()


def _sections():
    e = struct.unpack_from("<I", DATA, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", DATA, coff + 2)[0]
    optsz = struct.unpack_from("<H", DATA, coff + 16)[0]
    opt = coff + 20
    base = struct.unpack_from("<Q", DATA, opt + 24)[0]
    out = []
    for i in range(nsec):
        s = opt + optsz + i * 40
        vsize, va, rawsz, rawptr = struct.unpack_from("<IIII", DATA, s + 8)
        out.append((base + va, max(vsize, rawsz), rawptr, rawsz))
    return out


SECS = _sections()


def off_of(va):
    for sva, size, rawptr, rawsz in SECS:
        if sva <= va < sva + size:
            if va - sva >= rawsz:
                raise SystemExit(f"{va:#x}: file に無い (.bss)")
            return rawptr + (va - sva)
    raise SystemExit(f"{va:#x}: セクション外")


def rd(va, n):
    o = off_of(va)
    return DATA[o:o + n]


def dis(va, n):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    o = off_of(va)
    for ins in md.disasm(DATA[o:o + n * 15], va):
        print(f"{ins.address:#x}: {ins.mnemonic:8} {ins.op_str}")
        n -= 1
        if n <= 0:
            break


def desc(va, depth=0, seen=None):
    """型記述子 (0x416750 の機械語に合わせる): [0]=tag, [1]=base 相対, base+6=項目数(u32),
    項目 i は base+0xa+16i に項目型へのポインタ、その +8 (base+0x12+16i) に u32 オフセット。"""
    seen = set() if seen is None else seen
    if va in seen or depth > 3:
        return
    seen.add(va)
    tag = rd(va, 1)[0]
    base = va + rd(va + 1, 1)[0]
    count = struct.unpack("<I", rd(base + 6, 4))[0]
    print("  " * depth + f"desc {va:#x} tag={tag:#x} base={base:#x} count={count}")
    for i in range(min(count, 8)):
        slot = struct.unpack("<Q", rd(base + 0xA + 16 * i, 8))[0]
        foff = struct.unpack("<I", rd(base + 0x12 + 16 * i, 4))[0]
        fd = struct.unpack("<Q", rd(slot, 8))[0]
        ftag = rd(fd, 1)[0]
        print("  " * (depth + 1) + f"field[{i}] off={foff:#x} slot={slot:#x} desc={fd:#x} tag={ftag:#x}")
        if ftag == 0x0E:
            desc(fd, depth + 2, seen)


if __name__ == "__main__":
    cmd, va = sys.argv[1], int(sys.argv[2], 16)
    if cmd == "dis":
        dis(va, int(sys.argv[3]) if len(sys.argv) > 3 else 80)
    elif cmd == "desc":
        desc(va)
    else:
        raise SystemExit(__doc__)
