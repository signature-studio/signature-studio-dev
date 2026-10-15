#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の .text を 1 回線形走査し、item tag (PY-195 / #3403) の未確定点の件数を出す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_item_tag_scan.py

出す件数 (REPORT_PY195.md §2・§3 の数値の出どころ):
- P = 0x15e26a0 の読出し (mov reg, [P]) の件数と、読んだレジスタ経由の dword 書込み (12 命令以内)。
- 0x193fa10 (P の指す dword) への RIP 相対の参照。
- K = 0x16bacf0 の周辺 [K-0x200, K+0x20) を指す RIP 相対の参照の件数。
- bulk 複写: rep 系の命令 (rep/repne/repe/repz) と、memset の thunk (0x5e1120) の呼出しのうち、
  直前 40 命令 (かつ 96 バイト以内) に K 周辺 [K-0x200, K+0x20) を RIP 相対で指す命令があるものの件数。
線形走査のため、レジスタ経由の間接参照は数えない (限界は REPORT_PY195.md §3)。
"""
import os
import re
import sys
from collections import Counter

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP_RE = re.compile(r"\[rip \+ (0x[0-9a-f]+)\]")
MEM_RE = re.compile(r"^(dword|qword) ptr \[([a-z0-9]+)\]")
P_SLOT = 0x15E26A0
P_TGT = 0x193FA10
K = 0x16BACF0
MEMSET_THUNK = 0x5E1120
WINDOW = 40


def near_k(a, recent):
    hit = any(x[3] is not None and K - 0x200 <= x[3] < K + 0x20 for x in recent if a - x[0] <= 0x60)
    return 1 if hit else 0


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    code = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    tracked = {}
    recent = []
    p_loads = 0
    p_stores = []
    tgt_refs = 0
    k_nbr_refs = 0
    bulk = Counter()
    bulk_k = 0
    n = 0
    for ins in md.disasm(code, base + text.VirtualAddress):
        if ins.mnemonic == "int3":
            continue
        n += 1
        a = ins.address
        op = ins.op_str
        mn = ins.mnemonic
        m = RIP_RE.search(op)
        t = a + ins.size + int(m.group(1), 16) if m else None
        if t == P_TGT:
            tgt_refs += 1
        if t is not None and K - 0x200 <= t < K + 0x20:
            k_nbr_refs += 1
        mm = MEM_RE.match(op)
        if mn == "mov" and mm and mm.group(2) in tracked:
            p_stores.append((hex(a), hex(tracked[mm.group(2)][0]), op))
        dst = op.split(",")[0].strip() if "," in op else ""
        for r in list(tracked):
            if mn == "call" or tracked[r][1] >= 12 or dst == r:
                del tracked[r]
            else:
                tracked[r][1] += 1
        if mn == "mov" and t == P_SLOT and "," in op:
            reg = op.split(",")[0].strip()
            if reg.startswith(("r", "e")) and "ptr" not in reg:
                tracked[reg] = [a, 0]
                p_loads += 1
        if mn == "call" and op == hex(MEMSET_THUNK):
            bulk["memset_thunk"] += 1
            bulk_k += near_k(a, recent)
        if op.startswith("rep") or mn.startswith("rep"):
            bulk[mn] += 1
            bulk_k += near_k(a, recent)
        recent.append((a, mn, op, t))
        if len(recent) > WINDOW:
            recent.pop(0)
    print("instructions", n)
    print("P loads (mov reg, [P]):", p_loads)
    print("P-derived dword stores (12 insns window):", len(p_stores))
    for s in p_stores:
        print("  ", s[0], "site", s[1], s[2])
    print("RIP refs to P target 0x193fa10:", tgt_refs)
    print("RIP refs to K neighborhood [K-0x200, K+0x20):", k_nbr_refs)
    print("bulk copy sites:", dict(bulk), "total", sum(bulk.values()))
    print("bulk sites with a K-region RIP ref in the prior 40 insns:", bulk_k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
