#!/usr/bin/env python3
"""0x60c220 の間接呼出し `call qword ptr [rbx+0x80]` (rbx=obj) の +0x80 スロットへの書込み元を PE 全体で列挙する (PY-406)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_obj80_writers.py

出力: 書込み命令 (`mov qword ptr [reg+0x80], src`) の VA と、直前 9 命令の逆アセンブル。
線形走査が不正命令で止まるため、止まったら 1 バイト進めて再開する。
展開: fl-win64 素材 (oc_artifacts 名) を展開する。素材の展開先は REFERENCES の [WIN64] 参照。
"""
import os
import re

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
PAT = re.compile(r"^qword ptr \[(?!rbp|rsp|ebp|esp)(\w+) \+ 0x80\], ")
TARGET = "0x410090"


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits = []
    decoded = 0
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        code = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        va0 = base + s.VirtualAddress
        window = []
        pos = 0
        while pos < len(code):
            got = None
            for ins in md.disasm(code[pos:pos + 16], va0 + pos):
                got = ins
                break
            if got is None:
                pos += 1
                window = []
                continue
            decoded += 1
            pos += got.size
            window.append(got)
            if len(window) > 9:
                window.pop(0)
            if got.mnemonic == "mov" and PAT.match(got.op_str):
                hits.append((got.address, got.op_str, [(w.address, w.mnemonic, w.op_str) for w in window]))
    print(f"decoded={decoded} writes_to_nonframe+0x80={len(hits)}")
    for va, op, ctx in hits:
        if "0x410090" in " ".join(str(c[2]) for c in ctx) or op.endswith(TARGET):
            print(f"== {hex(va)} {op}")
            for a, m, o in ctx:
                print(f"   {hex(a)} {m} {o}")
    print("--- 0x410090 は 'call 0x410090' 直前の書込みとして:")
    for va, op, ctx in hits:
        print(f"  {hex(va)} {op}")


if __name__ == "__main__":
    main()
