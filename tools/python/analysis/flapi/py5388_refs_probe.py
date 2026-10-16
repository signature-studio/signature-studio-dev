#!/usr/bin/env python3
"""PY-5388 (#5771): linkToLastTweaked (PE 0xd76c90) の参照元を PE 静的に数える。

- rel32 (call/jmp) で 0xd76c90 を直接指す命令の数
- 8 byte 絶対ポインタで 0xd76c90 を指す場所の数 (PyMethodDef の meth 欄)
- その場所の PyMethodDef 項目 (name ptr・meth・flags) を読む

使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 py5388_refs_probe.py
PE は $FL_WIN64_DIR/extracted/block00031_PE.bin。
"""
import os
import struct
import sys

import pefile

TARGET = 0xD76C90
PE_PATH = os.path.join(
    os.environ.get("FL_WIN64_DIR", ""), "extracted", "block00031_PE.bin"
)


def read_cstr(pe, va):
    off = pe.get_offset_from_rva(va - pe.OPTIONAL_HEADER.ImageBase)
    data = bytes(pe.__data__)
    end = data.index(b"\0", off)
    return data[off:end].decode(errors="replace")


def main():
    if not os.path.exists(PE_PATH):
        print("PE が無い:", PE_PATH)
        return 2
    pe = pefile.PE(PE_PATH, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = bytes(pe.__data__)
    rel, absp = [], []
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        sva = base + s.VirtualAddress
        for i in range(len(raw) - 5):
            if raw[i] in (0xE8, 0xE9):
                disp = struct.unpack_from("<i", raw, i + 1)[0]
                if sva + i + 5 + disp == TARGET:
                    rel.append((name, sva + i))
        for i in range(0, len(raw) - 7, 8):
            if struct.unpack_from("<Q", raw, i)[0] == TARGET:
                absp.append(sva + i)
    print("rel32 call/jmp to 0xd76c90:", len(rel))
    for name, va in rel:
        print("  %s %#x" % (name, va))
    print("abs8 pointer to 0xd76c90:", len(absp))
    for va in absp:
        # PyMethodDef: {char* name; PyCFunction meth; int flags; char* doc}
        ent = va - 8
        name_ptr = struct.unpack("<Q", data[pe.get_offset_from_rva(ent - base):][:8])[0]
        flags = struct.unpack("<i", data[pe.get_offset_from_rva(va - base) + 8:][:4])[0]
        print("  meth 欄 %#x (項目 %#x) name=%s flags=%d" % (
            va, ent, read_cstr(pe, name_ptr), flags))
    return 0


if __name__ == "__main__":
    sys.exit(main())
