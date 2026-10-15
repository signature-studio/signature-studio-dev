#!/usr/bin/env python3
"""ildsp の関数 (RVA 範囲) の逆アセンブルと、.text 全体での [reg+DISP] 書込み元の列挙 (T-SH-131 / #5070)。

usage:
  ildsp_field_writers.py PE dis START END          # RVA 範囲 [START, END) を逆アセンブル
  ildsp_field_writers.py PE writers DISP           # [reg+DISP] を書く命令 (先頭オペランドがメモリ) を .text 全体で列挙
  ildsp_field_writers.py PE const RVA...           # RIP 相対で指される float32 を読む (rip 基準を次命令で補正する形は呼び出し側で行う)
既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin
"""
import sys, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

WRITE = {"mov", "movss", "movd", "movq", "movaps", "movups", "movdqu", "movdqa", "movsd",
         "add", "sub", "inc", "dec", "and", "or", "xor", "lea"}


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    sec = pe + 24 + opt
    out = []
    for i in range(nsec):
        o = sec + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode(errors="replace")
        vsize, va, rawsz, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, va, max(vsize, rawsz), rawptr))
    return out


def off(secs, rva):
    for _, va, sz, raw in secs:
        if va <= rva < va + sz:
            return raw + rva - va
    raise SystemExit(f"rva {rva:#x} is not mapped")


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    pe_path, mode = sys.argv[1], sys.argv[2]
    data = open(pe_path, "rb").read()
    secs = sections(data)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    if mode == "dis":
        start, end = int(sys.argv[3], 16), int(sys.argv[4], 16)
        blob = data[off(secs, start):off(secs, start) + (end - start)]
        for ins in md.disasm(blob, start):
            print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    elif mode == "writers":
        disp = int(sys.argv[3], 16)
        for name, va, sz, raw in secs:
            if name != ".text":
                continue
            for ins in md.disasm(data[raw:raw + sz], va):
                if ins.mnemonic not in WRITE or not ins.operands:
                    continue
                d = ins.operands[0]
                if d.type == 3 and d.mem.base != 0 and d.mem.index == 0 and d.mem.disp == disp:
                    print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    elif mode == "const":
        for a in sys.argv[3:]:
            rva = int(a, 16)
            f = struct.unpack_from("<f", data, off(secs, rva))[0]
            print(f"RVA {rva:#x}: float32 {f!r}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
