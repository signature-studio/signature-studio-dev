#!/usr/bin/env python3
"""FLEngine PE の指定 VA 範囲 [開始, 終了) の命令のうち RIP 相対メモリオペランドを列挙する (PY-103 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flag_slots.py <開始VA(16進)> <終了VA(16進)>

各行: 命令 VA・命令・スロット VA (次命令アドレス + disp)・分類 (store = 先頭オペランドがメモリ / lea / load)・
スロットの file 内初期値 (8 byte)。.bss など file に実体が無いスロットは bss と出す (起動時の値は未確定)。
範囲は関数の先頭から与える。線形走査で復号できないバイトは 1 バイト進めて再同期する。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def locate(pe, raw, base, va):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            if rva - s.VirtualAddress >= s.SizeOfRawData:
                return s.Name.rstrip(b"\0").decode(), None
            return s.Name.rstrip(b"\0").decode(), s.PointerToRawData + (rva - s.VirtualAddress)
    return None, None


def main():
    start, end = (int(a, 16) for a in sys.argv[1:3])
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    _, fo = locate(pe, raw, base, start)
    if fo is None:
        sys.exit("開始 VA が file 内の section に無い")
    code = raw[fo:fo + (end - start) + 16]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off = 0
    while start + off < end:
        ins = next(md.disasm(code[off:off + 16], start + off), None)
        if ins is None:
            off += 1
            continue
        m = RIP.search(ins.op_str)
        if m:
            slot = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            first = ins.op_str.split(",")[0]
            kind = "lea" if ins.mnemonic == "lea" else ("store" if "[rip" in first else "load")
            sec, sfo = locate(pe, raw, base, slot)
            init = raw[sfo:sfo + 8].hex() if sfo is not None else "bss"
            print(f"{hex(ins.address)} {ins.mnemonic} {ins.op_str} -> {hex(slot)} {kind} {sec} init={init}")
        off += ins.size


if __name__ == "__main__":
    main()
