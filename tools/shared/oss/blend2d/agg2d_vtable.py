#!/usr/bin/env python3
# AggCreateInstance が構築する Agg2D オブジェクトの vtable を実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> [AGG2D_BLOCK=block24356_PE.bin] python3 agg2d_vtable.py [出力 JSON]
# 依存: pefile, capstone (pip install pefile capstone)。出力の既定は tools/shared/work/ (gitignore)。
# AGG2D_BLOCK の既定は Blend2D.dll (block24339)。dsp_ippv2 (block24356) も AggCreateInstance を持つため比較に使う。
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
DLL_BLOCK = os.environ.get("AGG2D_BLOCK", "block24339_PE.bin")
# AggCreateInstance の逆アセンブルで確認した値 (REPORT_AGG2D.md §5)。block24339 の検証用。
KNOWN = {"block24339_PE.bin": (0x1800568A0, 0x1801DBEC0)}
# agg2d_callees.py・agg2d_lift_probe.py が import する値。既定以外の DLL では None になり、import 側が落ちる。
CTOR_VA, VTABLE_VA = KNOWN.get(DLL_BLOCK, (None, None))


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


def find_ctor_and_vtable(md, pe, data, base):
    # AggCreateInstance → (確保 call の後の) 末尾 jmp で ctor へ。ctor は先頭近くで
    # `lea reg,[rip+X]` → `mov [rcx],reg` の順に vtable を書く。
    exp = [e for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b"AggCreateInstance"]
    if not exp:
        sys.exit("AggCreateInstance の export が無い")
    rva = exp[0].address
    ctor = None
    for i in md.disasm(data[rva:rva + 0x40], base + rva, count=16):
        if i.mnemonic == "jmp" and i.op_str.startswith("0x"):
            ctor = int(i.op_str, 16)
            break
    if ctor is None:
        sys.exit("AggCreateInstance の末尾 jmp が見つからない")
    insns = list(md.disasm(data[ctor - base:ctor - base + 0x100], ctor, count=40))
    for a, b in zip(insns, insns[1:]):
        m = re.match(r"(\w+), \[rip \+ (0x[0-9a-f]+)\]$", a.op_str)
        if a.mnemonic == "lea" and m and b.mnemonic == "mov" and b.op_str == f"qword ptr [rcx], {m.group(1)}":
            return ctor, a.address + a.size + int(m.group(2), 16)
    sys.exit("ctor 内に vtable の書き込みが見つからない")


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    path = os.path.join(root, "extracted", DLL_BLOCK)
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    text_hi = text_lo + text.Misc_VirtualSize

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    CTOR_VA, VTABLE_VA = find_ctor_and_vtable(md, pe, data, base)
    if DLL_BLOCK in KNOWN and KNOWN[DLL_BLOCK] != (CTOR_VA, VTABLE_VA):
        sys.exit(f"検出値 {hex(CTOR_VA)}/{hex(VTABLE_VA)} が既知値と不一致")

    entries = []
    off = VTABLE_VA - base
    while True:
        v = struct.unpack_from("<Q", data, off + 8 * len(entries))[0]
        if not (text_lo <= v < text_hi):
            break
        entries.append(v)
    stop_value = struct.unpack_from("<Q", data, off + 8 * len(entries))[0]

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
