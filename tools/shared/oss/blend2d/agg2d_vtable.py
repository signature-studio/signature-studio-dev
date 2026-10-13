#!/usr/bin/env python3
# AggCreateInstance が構築する Agg2D オブジェクトの vtable を実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_vtable.py [出力 JSON]
# 依存: pefile, capstone (pip install pefile capstone)。出力の既定は tools/shared/work/ (gitignore)。
import json
import os
import re
import struct
import sys
from collections import Counter

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_vtable.json")
DLL_BLOCK = "block24339_PE.bin"
# AggCreateInstance の逆アセンブルで確認した値 (REPORT_AGG2D.md §5)。
CTOR_VA = 0x1800568A0
VTABLE_VA = 0x1801DBEC0


def classify(md, data, base, rva, text_lo, text_hi):
    insns = list(md.disasm(data[rva:rva + 16], base + rva, count=3))
    head = [i.mnemonic for i in insns]
    if not insns:
        return "empty"
    if head[0] == "jmp" and insns[0].op_str.startswith("0x"):
        return "thunk_jmp"
    if head[0] == "ret" or (len(head) >= 2 and head[1] == "ret" and head[0] in ("xor", "mov")):
        return "trivial_ret"
    if head[0] == "int3":
        return "int3"
    return "code"


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    path = os.path.join(root, "extracted", DLL_BLOCK)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    text_hi = text_lo + text.Misc_VirtualSize

    entries = []
    off = VTABLE_VA - base
    while True:
        v = struct.unpack_from("<Q", data, off + 8 * len(entries))[0]
        if not (text_lo <= v < text_hi):
            break
        entries.append(v)
    stop_value = struct.unpack_from("<Q", data, off + 8 * len(entries))[0]

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    uniq = sorted(set(entries))
    kinds = {}
    for v in uniq:
        kinds[v] = classify(md, data, base, v - base, text_lo, text_hi)

    result = {
        "dll_block": DLL_BLOCK,
        "ctor_va": hex(CTOR_VA),
        "vtable_va": hex(VTABLE_VA),
        "entries": len(entries),
        "unique_targets": len(uniq),
        "terminator_value": hex(stop_value),
        "kinds_over_unique": dict(Counter(kinds.values())),
        "kinds_over_entries": dict(Counter(kinds[v] for v in entries)),
        "slot_targets": [hex(v) for v in entries],
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("entries", "unique_targets", "terminator_value", "kinds_over_unique", "kinds_over_entries")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
