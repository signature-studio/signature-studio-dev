#!/usr/bin/env python3
# CFG 間接 call / tail jmp (`call|jmp [GuardCFDispatchFunctionPointer]`) の直前で rax が定義されているかを実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_cfg_rax.py [出力 JSON]
# 依存: pefile, capstone。出力の既定は tools/shared/work/ (gitignore)。
# MSVC CFG は target を rax に入れて slot を呼ぶ (slot の先は jmp rax の thunk)。rax-in 方式の前提を確かめる。
# 負例: slot + 8 を同じ検出器に入れ、0 件であることを確かめる (外れたら rc=1)。
import json
import os
import struct
import sys
from collections import Counter

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from agg2d_vtable import DLL_BLOCK  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_cfg_rax.json")
WINDOW = 96
RAX_FAMILY = {capstone.x86.X86_REG_RAX, capstone.x86.X86_REG_EAX, capstone.x86.X86_REG_AX,
              capstone.x86.X86_REG_AL, capstone.x86.X86_REG_AH}


def writes_rax(insn):
    """明示 operand (宛先) と暗黙の書き込みの両方で rax 族への書き込みを判定する。"""
    if set(insn.regs_write) & RAX_FAMILY:
        return True
    ops = insn.operands
    return bool(ops) and ops[0].type == capstone.x86.X86_OP_REG and ops[0].reg in RAX_FAMILY \
        and bool(ops[0].access & capstone.CS_AC_WRITE)


def find_sites(md, data, base, text_lo, text_hi, slot):
    """rip 相対で slot を指す call/jmp を、バイト走査 + capstone の再確認で集める。"""
    sites = []
    for i in range(text_lo - base, text_hi - base - 6):
        if data[i] != 0xFF or data[i + 1] not in (0x15, 0x25):
            continue
        va = base + i
        insn = next(md.disasm(data[i:i + 16], va, count=1), None)
        if insn is None or insn.size != 6 or insn.mnemonic not in ("call", "jmp"):
            continue
        op = insn.operands[0]
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            if va + insn.size + op.mem.disp == slot:
                sites.append((va, insn.mnemonic))
    return sites


def preceding(md, data, base, va):
    """va で命令境界が揃う直線列のうち最も長いものを返す (va の直前 WINDOW バイトから同期を取る)。"""
    best = []
    for back in range(1, WINDOW + 1):
        cur, seq = va - back, []
        while cur < va:
            insn = next(md.disasm(data[cur - base:cur - base + 16], cur, count=1), None)
            if insn is None:
                break
            seq.append(insn)
            cur += insn.size
        if cur == va and seq:
            best = seq
    return best


def classify(seq):
    """seq の末尾から rax を書く最後の命令を探し、その形と、間に分岐・ret があるかを返す。"""
    branch = False
    for dist, insn in enumerate(reversed(seq), start=1):
        if insn.mnemonic == "call":
            return "call_return", dist, branch
        if writes_rax(insn):
            ops = insn.operands
            if insn.mnemonic in ("mov", "movabs", "movzx", "movsx", "movsxd", "lea", "xor") and len(ops) == 2:
                src = ops[1].type
                kind = {capstone.x86.X86_OP_REG: "reg", capstone.x86.X86_OP_MEM: "mem",
                        capstone.x86.X86_OP_IMM: "imm"}.get(src, "other")
                return "%s_%s" % (insn.mnemonic, kind), dist, branch
            return "other:" + insn.mnemonic, dist, branch
        if insn.mnemonic.startswith("j") or insn.mnemonic.startswith("ret"):
            branch = True
    return "live_in", None, branch


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
    lc = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
    slot = lc.GuardCFDispatchFunctionPointer
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    thunk = struct.unpack_from("<Q", data, slot - base)[0]
    thunk_bytes = bytes(data[thunk - base:thunk - base + 2])
    sites = find_sites(md, data, base, text_lo, text_hi, slot)
    control = find_sites(md, data, base, text_lo, text_hi, slot + 8)

    kinds, dists, synced, classes_by_mn, branched = Counter(), Counter(), 0, Counter(), 0
    per_site = []
    for va, mn in sites:
        seq = preceding(md, data, base, va)
        synced += 1 if len(seq) >= 4 else 0
        kind, dist, branch = classify(seq) if seq else ("no_sync", None, False)
        kinds[kind] += 1
        dists[dist] += 1
        classes_by_mn[mn] += 1
        branched += 1 if branch else 0
        per_site.append({"va": hex(va), "mnemonic": mn, "rax_def": kind, "distance": dist,
                         "branch_between": branch, "window": len(seq)})

    result = {
        "dll_block": DLL_BLOCK,
        "cfg_slot_va": hex(slot),
        "thunk_va": hex(thunk),
        "thunk_bytes": thunk_bytes.hex(),
        "sites_call_or_jmp": len(sites),
        "sites_by_mnemonic": dict(classes_by_mn),
        "sites_with_sync_window_ge4": synced,
        "sites_with_branch_between_def_and_site": branched,
        "rax_def_kinds": dict(kinds.most_common()),
        "rax_def_distance": {str(k): v for k, v in sorted(dists.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))},
        "negative_control_slot_plus8_sites": len(control),
        "sites": per_site,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    summary = {k: result[k] for k in ("cfg_slot_va", "thunk_va", "thunk_bytes", "sites_call_or_jmp",
                                      "sites_by_mnemonic", "sites_with_sync_window_ge4", "sites_with_branch_between_def_and_site", "rax_def_kinds",
                                      "negative_control_slot_plus8_sites")}
    print(json.dumps(summary, ensure_ascii=False))
    if len(control) != 0 or thunk_bytes != b"\xff\xe0":
        sys.exit(1)


if __name__ == "__main__":
    main()
