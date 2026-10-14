#!/usr/bin/env python3
"""FLEngine PE の flrack.Rack 属性表 (name・type・offset・flags・doc の 40 byte 行) を読む (PY-166 #3176 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_rack_probe.py [属性名 ...]

既定の属性名は loop_starter_config。各名前の char* を指す qword を .data 上で探し、その行の前後を
名前が 0 になる終端まで読んで表示する。type の値は CPython の PyMemberDef の T_* 番号に対応する
(0x01 = T_INT・0x03 = T_FLOAT・0x10 = T_OBJECT_EX)。offset は全行 0 で、値の格納先は表からは読めない。
"""
import os
import re
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DEFAULT_NAMES = ["loop_starter_config"]
TYPE_NAMES = {0x01: "T_INT", 0x03: "T_FLOAT", 0x10: "T_OBJECT_EX"}


def main():
    names = sys.argv[1:] or DEFAULT_NAMES
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def off2va(off):
        for v, vs, praw, rs in secs:
            if praw <= off < praw + rs:
                return base + v + (off - praw)
        return None

    def va2off(va):
        rva = va - base
        for v, vs, praw, rs in secs:
            if v <= rva < v + max(vs, rs):
                return praw + (rva - v)
        return None

    def qword(va):
        o = va2off(va)
        return struct.unpack_from("<Q", raw, o)[0] if o is not None else None

    def cstr(va):
        o = va2off(va)
        if o is None:
            return None
        e = raw.find(b"\0", o, o + 80)
        return raw[o:e].decode("latin1") if e > o else None

    for name in names:
        strs = [off2va(m.start()) for m in re.finditer(re.escape(name.encode() + b"\0"), raw)]
        strs = [s for s in strs if s is not None]
        for sva in strs:
            # 名前ポインタを指す qword (表の先頭行の name)
            hits = [off for off in range(0, len(raw) - 8, 8)
                    if struct.unpack_from("<Q", raw, off)[0] == sva]
            for off in hits:
                row_va = off2va(off)
                if row_va is None:
                    continue
                print(f"# {name}: string VA {sva:#x}, row {row_va:#x}")
                start = row_va
                while True:
                    prev = start - 40
                    if qword(prev) in (None, 0) or cstr(qword(prev)) is None:
                        break
                    start = prev
                va = start
                while True:
                    nm = qword(va)
                    if not nm:
                        break
                    typ = qword(va + 8) & 0xFFFFFFFF
                    print(f"  {va:#x} name={cstr(nm)!r} type={typ:#x}({TYPE_NAMES.get(typ, '?')})"
                          f" offset={qword(va + 16):#x} flags={qword(va + 24):#x} doc={qword(va + 32):#x}")
                    va += 40


if __name__ == "__main__":
    main()
