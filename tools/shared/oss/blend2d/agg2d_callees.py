#!/usr/bin/env python3
# Agg2D vtable の各関数が (推移的に) 呼ぶ先を実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_callees.py [出力 JSON]
# 依存: pefile, capstone。出力の既定は tools/shared/work/ (gitignore)。
# agg2d_vtable.py と同じ DLL・同じ vtable 位置を使う。
# 各 vtable 関数から直接 call / jmp で到達できる内部関数を再帰的に辿り、到達した KERNEL32 import を集計する。
import json
import os
import struct
import sys
from collections import Counter

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from agg2d_vtable import CTOR_VA, DLL_BLOCK, VTABLE_VA  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_callees.json")
MAX_FUNCS = 4000
MAX_INSNS = 200000


def load_entries(data, base, text_lo, text_hi):
    entries = []
    off = VTABLE_VA - base
    while True:
        v = struct.unpack_from("<Q", data, off + 8 * len(entries))[0]
        if not (text_lo <= v < text_hi):
            break
        entries.append(v)
    return entries


def import_map(pe):
    names = {}
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dll = entry.dll.decode("ascii", "replace")
        for imp in entry.imports:
            name = imp.name.decode("ascii", "replace") if imp.name else "ord%d" % imp.ordinal
            names[imp.address] = "%s!%s" % (dll, name)
    return names


def scan_function(md, data, base, start, text_lo, text_hi, iat):
    """start から分岐を辿って到達する命令を読む。返り値: (内部 call/jmp 先, import 名)。"""
    internal, imports = set(), set()
    todo, seen = [start], set()
    while todo and len(seen) < MAX_INSNS:
        va = todo.pop()
        while va not in seen and text_lo <= va < text_hi:
            seen.add(va)
            insn = next(md.disasm(data[va - base:va - base + 16], va, count=1), None)
            if insn is None:
                break
            nxt = va + insn.size
            m = insn.mnemonic
            op = insn.operands[0] if insn.operands else None
            if m in ("ret", "int3"):
                break
            if m == "call" or m == "jmp":
                if op is not None and op.type == capstone.x86.X86_OP_IMM:
                    if text_lo <= op.imm < text_hi:
                        if m == "call":
                            internal.add(op.imm)
                        else:
                            todo.append(op.imm)
                elif op is not None and op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    slot = nxt + op.mem.disp
                    imports.add(iat.get(slot, "unresolved@%x" % slot))
                if m == "jmp":
                    break
                va = nxt
                continue
            if m.startswith("j") and op is not None and op.type == capstone.x86.X86_OP_IMM:
                todo.append(op.imm)
            va = nxt
    return internal, imports


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    pe = pefile.PE(os.path.join(root, "extracted", DLL_BLOCK), fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    text_hi = text_lo + text.Misc_VirtualSize
    iat = import_map(pe)
    lc = getattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG", None)
    if lc is not None:
        iat[lc.struct.GuardCFDispatchFunctionPointer] = "CFG!GuardCFDispatch"
        iat[lc.struct.GuardCFCheckFunctionPointer] = "CFG!GuardCFCheck"

    entries = load_entries(data, base, text_lo, text_hi)
    roots = sorted(set(entries))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    cache = {}

    def get(fn):
        if fn not in cache:
            cache[fn] = scan_function(md, data, base, fn, text_lo, text_hi, iat)
        return cache[fn]

    reach = {}
    for r in roots:
        seen, imports, stack = set(), set(), [r]
        while stack and len(seen) < MAX_FUNCS:
            f = stack.pop()
            if f in seen:
                continue
            seen.add(f)
            internal, imps = get(f)
            imports |= imps
            stack.extend(internal - seen)
        reach[r] = (seen, imports)

    owners = Counter()
    for seen, _ in reach.values():
        owners.update(seen)
    per_root = {}
    for r in roots:
        seen, imports = reach[r]
        exclusive = sum(1 for f in seen if owners[f] == 1)
        per_root[hex(r)] = {
            "reachable_funcs": len(seen),
            "exclusive_funcs": exclusive,
            "imports": sorted(imports),
        }

    import_count = Counter()
    for v in per_root.values():
        import_count.update(v["imports"])
    shared_funcs = sum(1 for f, c in owners.items() if c >= 2)
    result = {
        "dll_block": DLL_BLOCK,
        "ctor_va": hex(CTOR_VA),
        "vtable_va": hex(VTABLE_VA),
        "unique_roots": len(roots),
        "roots_reaching_import": sum(1 for v in per_root.values() if v["imports"]),
        "distinct_funcs_reached": len(owners),
        "funcs_shared_by_2plus_roots": shared_funcs,
        "distinct_imports": len(import_count),
        "imports_by_root_count": dict(import_count.most_common()),
        "per_root": per_root,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    summary = {k: result[k] for k in ("unique_roots", "roots_reaching_import", "distinct_funcs_reached", "funcs_shared_by_2plus_roots", "distinct_imports")}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
