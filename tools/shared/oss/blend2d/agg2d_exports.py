#!/usr/bin/env python3
# fl-win64 内で AggCreateInstance を export する PE を列挙し、各 DLL の export 数と
# AggCreateInstance の先頭命令を出す (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_exports.py
# 依存: pefile, capstone。
import os
import sys

import capstone
import pefile

ROOT = os.environ.get("FL_WIN64_DIR")
if not ROOT:
    sys.exit("FL_WIN64_DIR を設定してください")
EXTRACTED = os.path.join(ROOT, "extracted")
TARGET = b"AggCreateInstance"


def find_pe_files(top):
    for dirpath, _, files in os.walk(top):
        for name in files:
            if name.endswith("_PE.bin"):
                yield os.path.join(dirpath, name)


def main():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits = 0
    for path in sorted(find_pe_files(EXTRACTED)):
        try:
            pe = pefile.PE(path, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        except pefile.PEFormatError:
            continue
        if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            continue
        syms = [s for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name]
        agg = [s for s in syms if s.name == TARGET]
        if not agg:
            continue
        hits += 1
        base = pe.OPTIONAL_HEADER.ImageBase
        rva = agg[0].address
        off = pe.get_offset_from_rva(rva)
        code = pe.__data__[off:off + 16]
        head = [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(code, base + rva, 3)]
        sec = [x.Name.rstrip(b"\0").decode(errors="replace") for x in pe.sections]
        rel = os.path.relpath(path, EXTRACTED)
        print(f"{rel}\texports={len(syms)}\tAggCreateInstance=0x{base + rva:x}\tsections={','.join(sec)}")
        print(f"  head: {' ; '.join(head)}")
    print(f"PE with AggCreateInstance export: {hits}")


if __name__ == "__main__":
    main()
