#!/usr/bin/env python3
# Blend2D.dll (block24339) と dsp_ippv2 (block24356) の AggCreateInstance の vtable を slot 単位で突き合わせる (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_vtable_cmp.py [出力 JSON]
# 依存: pefile, capstone。agg2d_vtable.py の find_ctor_and_vtable を流用する。
# 出力の既定は tools/shared/work/ (gitignore)。
import collections
import json
import os
import re
import sys

import capstone
import pefile

from agg2d_vtable import find_ctor_and_vtable

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_vtable_cmp.json")
BLOCKS = {"blend2d": "block24339_PE.bin", "agg_ippv2": "block24356_PE.bin"}


def body_kind(md, data, base, va):
    insns = list(md.disasm(data[va - base:va - base + 16], va, count=3))
    if not insns:
        return "empty"
    head = [(i.mnemonic, i.op_str) for i in insns]
    if head[0][0] == "ret":
        return "noop_ret"
    if head[0][0] == "jmp" and head[0][1].startswith("0x"):
        return "thunk_jmp"
    if len(head) >= 2 and head[1][0] == "ret":
        if head[0] == ("xor", "eax, eax") or (head[0][0] == "mov" and re.fullmatch(r"eax, 0x[0-9a-f]+|eax, \d+", head[0][1])):
            return "ret_const"
        if head[0][0] == "mov" and re.match(r"(byte|word|dword|qword) ptr \[", head[0][1]):
            return "store_ret"
    return "code"


def load(root, block):
    path = os.path.join(root, "extracted", block)
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    text_hi = text_lo + text.Misc_VirtualSize
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    _, vt = find_ctor_and_vtable(md, pe, data, base)
    slots = []
    off = vt - base
    while True:
        v = int.from_bytes(data[off + 8 * len(slots):off + 8 * len(slots) + 8], "little")
        if not (text_lo <= v < text_hi):
            break
        slots.append(v)
    kinds = {v: body_kind(md, data, base, v) for v in set(slots)}
    return slots, kinds


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    slots_a, kinds_a = load(root, BLOCKS["blend2d"])
    slots_b, kinds_b = load(root, BLOCKS["agg_ippv2"])
    if len(slots_a) != len(slots_b):
        sys.exit(f"slot 数が不一致: {len(slots_a)} vs {len(slots_b)}")

    pairs = collections.Counter()
    for i, (va, vb) in enumerate(zip(slots_a, slots_b)):
        pairs[(kinds_a[va], kinds_b[vb])] += 1
    noop_a = [i for i, v in enumerate(slots_a) if kinds_a[v] == "noop_ret"]
    shared_a = collections.Counter(slots_a)
    summary = {
        "slots": len(slots_a),
        "blend2d": {
            "unique": len(set(slots_a)),
            "kinds_over_slots": dict(collections.Counter(kinds_a[v] for v in slots_a)),
            "noop_ret_slots": len(noop_a),
            "noop_ret_target": hex(slots_a[noop_a[0]]) if noop_a else None,
            "most_shared": [[hex(v), n] for v, n in shared_a.most_common(3)],
        },
        "agg_ippv2": {
            "unique": len(set(slots_b)),
            "kinds_over_slots": dict(collections.Counter(kinds_b[v] for v in slots_b)),
        },
        "crosstab_blend2d_x_agg": {f"{a}|{b}": n for (a, b), n in sorted(pairs.items())},
        "noop_ret_slot_indices": noop_a,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
