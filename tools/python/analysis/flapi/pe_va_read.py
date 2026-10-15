#!/usr/bin/env python3
"""指定 VA の PE ファイル上の値を読む (PY-169 / #3212 の解析補助)。所属セクション・ファイル上の 8/4 バイト整数・C 文字列を出す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_va_read.py <VA(16進)>[,<VA(16進)>...]

- セクション外・BSS (ファイル上に無い領域) は `not-in-file` と出す (値は 0 扱いにしない)。
- 値は PE ファイル上の初期値であり、実行時の値ではない。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData,
             s.Name.rstrip(b"\0").decode(errors="replace")) for s in pe.sections]
    for x in sys.argv[1].split(","):
        va = int(x, 16)
        rva = va - base
        hit = None
        for vaddr, vsz, praw, rsz, name in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                hit = (vaddr, vsz, praw, rsz, name)
                break
        if hit is None:
            print(hex(va), "section=none")
            continue
        vaddr, vsz, praw, rsz, name = hit
        off = rva - vaddr
        if off >= rsz:
            print(hex(va), f"section={name} not-in-file (bss)")
            continue
        fo = praw + off
        q = raw[fo:fo + 8]
        d = struct.unpack("<I", raw[fo:fo + 4])[0]
        s = raw[fo:fo + 48].split(b"\0")[0]
        print(hex(va), f"section={name} file_off={hex(fo)} qword={hex(struct.unpack('<Q', q.ljust(8, b'\0'))[0])}"
              f" dword={d} cstr={s!r}")


if __name__ == "__main__":
    main()
