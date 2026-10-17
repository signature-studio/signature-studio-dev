#!/usr/bin/env python3
"""transport jog・marker 系 4 関数 (continuousMove・continuousMovePos・markerJumpJog・markerSelJog) の
PyMethodDef 記録 (name・fn VA・flags・doc) を FLEngine PE から引く (PY-4852 / #5048 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_jog4_va_probe.py

展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
- name 文字列の VA を指す 8 byte ポインタを PE 全体から探し、その位置を 32 バイト記録の先頭とみなす。
- 出力の flags は kwsig.flags (flapi_table.json) と一致するはず (continuousMove 系 1、jog marker 系 3)。
"""
import os
import struct

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
NAMES = ["continuousMove", "continuousMovePos", "markerJumpJog", "markerSelJog"]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def v2o(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + max(vs, rs):
                return p + (rva - v)
        return None

    def o2v(fo):
        for v, vs, p, rs in secs:
            if p <= fo < p + rs:
                return base + v + (fo - p)
        return None

    def cstr(va):
        fo = v2o(va) if va else None
        if fo is None:
            return None
        e = raw.find(b"\0", fo, fo + 200)
        return raw[fo:e].decode(errors="replace") if e != -1 else None

    for nm in NAMES:
        needle = nm.encode() + b"\0"
        i = raw.find(needle)
        while i != -1:
            sva = o2v(i)
            ptr = struct.pack("<Q", sva) if sva is not None else None
            j = raw.find(ptr, 0) if ptr else -1
            while j != -1:
                _, fn, flags = struct.unpack_from("<QQi", raw, j)
                doc = struct.unpack_from("<Q", raw, j + 24)[0]
                print(f"{nm:20s} name_va={sva:#x} record_fo={j:#x} fn={fn:#x} "
                      f"flags={flags} doc={cstr(doc)!r}")
                j = raw.find(ptr, j + 1)
            i = raw.find(needle, i + 1)


if __name__ == "__main__":
    main()
