#!/usr/bin/env python3
"""channel の grid 構造体ポインタ (+0x7ac) の書込み元と、その生成経路を PE 全 .text の線形走査で列挙する (PY-101 #2878)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_grid_writers.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
出力: +0x7ac へのメモリ書込み (mov [reg+0x7ac], ...) の一覧、grid 生成関数 0xff63f0 の呼出し元、
      channel 生成関数 0xff5aa0 の呼出し元。約 30 秒 (capstone の線形走査。無効バイトは 1 byte 送りで読み飛ばす)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DISP = "+ 0x7ac]"
GRID_NEW = 0xFF63F0
CHAN_NEW = 0xFF5AA0


def sweep(raw, pe):
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            for ins in md.disasm(data[off:off + 16], start + off, 1):
                yield ins
                off += ins.size
                break
            else:
                off += 1


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    writes = []
    callers = {GRID_NEW: [], CHAN_NEW: []}
    for ins in sweep(raw, pe):
        t = ins.op_str
        if ins.mnemonic == "mov" and DISP in t and t.split(",")[0].endswith("]"):
            writes.append((ins.address, t))
        if ins.mnemonic == "call":
            tgt = t.strip().lower()
            for k in callers:
                if tgt == hex(k):
                    callers[k].append(ins.address)
    print("+0x7ac 書込み (mov [reg+0x7ac], ...):")
    for a, t in writes:
        print("  %s  %s" % (hex(a), t))
    print("grid 生成 0xff63f0 の直接 call 元: " + " ".join(hex(a) for a in callers[GRID_NEW]))
    print("channel 生成 0xff5aa0 の直接 call 元: " + " ".join(hex(a) for a in callers[CHAN_NEW]))
    print("+0x7ac 書込み件数: %d" % len(writes))


if __name__ == "__main__":
    sys.exit(main())
