#!/usr/bin/env python3
"""FLEngine PE の flcpt.CPT 属性表 (name・type・offset・flags・doc の 40 byte 行) を読む (PY-164 #3174 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flcpt_cpt_probe.py [属性名 ...]

既定の属性名は resolution・genre。pe_flrack_rack_probe.py と同じ方式で、名前の char* を指す qword の行から
前後を終端 (name が 0 の行 / 名前ポインタでない行) まで読み、全行を表にする。type は PyMemberDef の T_* 番号
(0x01 = T_INT・0x03 = T_FLOAT・0x0e = T_BOOL・0x10 = T_OBJECT_EX)。offset・flags は表から読めた値をそのまま出す。
名前が表に無いときは『表に無し』と出す (表の外に同名の属性があるかは、この probe では判定しない)。
"""
import os
import re
import struct
import sys
from collections import Counter

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DEFAULT_NAMES = ["resolution", "genre"]
TYPE_NAMES = {0x01: "T_INT", 0x03: "T_FLOAT", 0x0E: "T_BOOL", 0x10: "T_OBJECT_EX"}


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

    def rows_of(row_va):
        start = row_va
        while True:
            prev = start - 40
            if qword(prev) in (None, 0) or cstr(qword(prev)) is None:
                break
            start = prev
        rows = []
        va = start
        while True:
            nm = qword(va)
            if not nm:
                break
            rows.append(va)
            va += 40
        return rows

    for name in names:
        strs = [off2va(m.start()) for m in re.finditer(re.escape(name.encode() + b"\0"), raw)]
        strs = [s for s in strs if s is not None]
        found = False
        for sva in strs:
            hits = [off for off in range(0, len(raw) - 8, 8)
                    if struct.unpack_from("<Q", raw, off)[0] == sva]
            for off in hits:
                row_va = off2va(off)
                if row_va is None:
                    continue
                rows = rows_of(row_va)
                if not rows:
                    continue
                found = True
                print(f"# {name}: string VA {sva:#x}, row {row_va:#x}, 表 {len(rows)} 行 "
                      f"({rows[0]:#x}〜{rows[-1]:#x})")
                tc = Counter()
                for va in rows:
                    typ = qword(va + 8) & 0xFFFFFFFF
                    tc[TYPE_NAMES.get(typ, hex(typ))] += 1
                    print(f"  {va:#x} name={cstr(qword(va))!r} type={typ:#x}({TYPE_NAMES.get(typ, '?')})"
                          f" offset={qword(va + 16):#x} flags={qword(va + 24):#x} doc={qword(va + 32):#x}")
                print(f"# type 内訳: {dict(tc)}")
                break
            if found:
                break
        if not found:
            print(f"# {name}: 属性表に無し (文字列 {len(strs)} 件のいずれも行の名前ポインタとして参照されない)")


if __name__ == "__main__":
    main()
