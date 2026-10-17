#!/usr/bin/env python3
"""PY-4914 (#5348): vptr 候補 0xed0bb0 / 0xed0c28 が、命令の即値・RIP 相対参照・データ領域の 4 byte 値として格納されるかを数える (block00031)。

  FL_WIN64_DIR=<展開先> python3 analysis/py4914_imm_data_scan.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
検査:
  - .text の非分岐命令の即値・RIP 相対の番地が候補 (相対形・絶対形 ImageBase+相対) と一致するか。
  - 分岐命令 (call/jmp/jcc) の飛び先は格納ではないので別に数える (表示のみ)。
  - .text 以外のセクションの 4 byte 値が候補 (相対形・絶対形) と一致するか。
陽性対照: 0x13acb88 の RIP 相対 lea (0x44a867) を検出しなければならない。
限界: 関数単位の値の伝播は見ない (py4914_vptr_fn_scan.py の範囲)。動的に計算した番地は見えない。
期待値と異なれば rc 1 (候補の格納 1 件以上)・陽性対照の不検出は rc 2。
"""
import os
import struct
import sys
import time

import capstone
import pefile

MAIN = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
MASK = (1 << 64) - 1
CHUNK = 1 << 16
X86 = capstone.x86
CANDIDATES = (0xED0BB0, 0xED0C28)
CONTROL = 0x13ACB88


def text_hits(pe, raw, md, want):
    base = pe.OPTIONAL_HEADER.ImageBase
    t = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    start = base + t.VirtualAddress
    n = min(t.Misc_VirtualSize, t.SizeOfRawData)
    data = raw[t.PointerToRawData:t.PointerToRawData + n]
    hits, branches, total, off = [], [], 0, 0
    while off < n:
        end = off
        for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
            if ins.address - start - off + ins.size > CHUNK:
                break
            total += 1
            end = ins.address - start + ins.size
            is_branch = ins.mnemonic.startswith(("call", "j"))
            for o in ins.operands:
                if o.type == X86.X86_OP_IMM and (o.imm & MASK) in want:
                    dst = branches if is_branch else hits
                    dst.append((ins.address, want[o.imm & MASK], ins.mnemonic + " " + ins.op_str))
                elif o.type == X86.X86_OP_MEM and o.mem.base == X86.X86_REG_RIP:
                    tgt = (ins.address + ins.size + o.mem.disp) & MASK
                    if tgt in want:
                        hits.append((ins.address, want[tgt], "rip " + ins.op_str))
        off = end if end > off else off + 1
    return total, hits, branches


def data_hits(pe, raw, want4):
    base = pe.OPTIONAL_HEADER.ImageBase
    hits = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode()
        if name == ".text":
            continue
        d = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        for i in range(0, len(d) - 3, 4):
            v4 = struct.unpack_from("<I", d, i)[0]
            if v4 in want4:
                hits.append((base + s.VirtualAddress + i, want4[v4], "dword in " + name))
    return hits


def main():
    t0 = time.time()
    raw = open(MAIN, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    base = pe.OPTIONAL_HEADER.ImageBase
    want = {}
    for v in CANDIDATES:
        want[v] = "cand 0x%x" % v
        want[base + v] = "cand 0x%x (abs)" % v
    want[CONTROL] = "control"
    want[base + CONTROL] = "control"
    total, th, tb = text_hits(pe, raw, md, want)
    want4 = {k: v for k, v in want.items() if k <= 0xFFFFFFFF and v != "control"}
    dh = data_hits(pe, raw, want4)
    print("block00031 insns=%d sec=%.1f" % (total, time.time() - t0))
    for a, lab, desc in th:
        print("TEXT %s at 0x%x: %s" % (lab, a, desc))
    for a, lab, desc in dh:
        print("DATA %s at 0x%x: %s" % (lab, a, desc))
    for a, lab, desc in tb:
        print("BRANCH-TARGET %s at 0x%x: %s (飛び先のみ・格納ではない)" % (lab, a, desc))
    ctrl = [h for h in th if h[1] == "control" and h[0] == 0x44A867]
    if not ctrl:
        print("control FAIL: 0x44a867 の lea を検出できない")
        return 2
    print("control PASS: 0x44a867 で検出")
    cand = [h for h in th + dh if h[1] != "control"]
    print("candidate store-like occurrences=%d" % len(cand))
    return 0 if not cand else 1


if __name__ == "__main__":
    sys.exit(main())
