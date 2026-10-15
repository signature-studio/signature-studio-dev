#!/usr/bin/env python3
"""PY-223 (#3627): 0xed4b70 (0x12da6d0 の唯一の呼出し元) を間接に呼ぶ候補の所在と、関数単位の参照を PE から集計する。

  FL_WIN64_DIR=<展開先> python3 analysis/py223_indirect_callers.py [--mutate]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
.text を 1 回だけ線形走査し、関数 (int3 パディングの直後の先頭) ごとに次を集める:
  - 間接 call `call qword ptr [reg + disp]` の disp
  - RIP 相対で指す VA が T (行テーブル 0x193fcf8 付近)・G1 (0x15d51a0)・flag セル (0x15e14a0) に当たる参照
表の所在 (0xed4b70 を含む連続した .text 内の関数ポインタ列) と、表を指すデータ上の値 (aligned qword) も出す。
--mutate: 表の検査 (添字 51 が 0xed4b70) を 1 件壊して FAIL することを確かめる (ネガティブコントロール)。
"""
import os
import struct
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_INVALID, X86_REG_RIP

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
TARGET = 0xED4B70
CALLER = 0x12DA6D0
T_RANGE = (0x193FC00, 0x193FE00)
G1 = 0x15D51A0
FLAG_CELL = 0x15E14A0
OFFSETS = (0x120, 0x198)


def main():
    mutate = "--mutate" in sys.argv
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    lo = base + text.VirtualAddress
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    hi = lo + n
    data = raw[text.PointerToRawData:text.PointerToRawData + n]

    def fo(va):
        return va - lo + text.PointerToRawData

    def qword(va):
        return struct.unpack_from("<Q", raw, fo(va))[0]

    # 表: TARGET を含む .text 内の連続した qword 列 (値が .text の VA)
    hits = []
    pos = raw.find(struct.pack("<Q", TARGET))
    while pos != -1:
        hits.append(pos)
        pos = raw.find(struct.pack("<Q", TARGET), pos + 1)
    entry = [lo + (p - text.PointerToRawData) for p in hits if text.PointerToRawData <= p < text.PointerToRawData + n]
    entry = entry[0]
    start = entry
    while lo <= qword(start - 8) < hi:
        start -= 8
    end = entry
    while lo <= qword(end) < hi:
        end += 8
    table = [qword(va) for va in range(start, end, 8)]
    if mutate:
        table[(entry - start) // 8] ^= 0x10
    idx_t = (entry - start) // 8
    ok_table = table[idx_t] == TARGET
    print(f"table {hex(start)}..{hex(end)} entries {len(table)} index({hex(TARGET)}) = {idx_t} "
          f"(offset {hex(idx_t * 8)}) {'PASS' if ok_table else 'FAIL'} table.check")

    # 表を指す aligned qword (表の外) と、表を指す参照 (コード)
    ptrs = []
    target_refs = 0
    for s in pe.sections:
        d = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        for o in range(0, len(d) - 7, 8):
            v = struct.unpack_from("<Q", d, o)[0]
            addr = base + s.VirtualAddress + o
            if v == TARGET:
                target_refs += 1
            if start <= v < end and not (start <= addr < end):
                ptrs.append((addr, v))
    print(f"aligned qword -> table (outside table): {[(hex(a), hex(v)) for a, v in ptrs]}")
    print(f"aligned qword == {hex(TARGET)} in all sections: {target_refs}")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    func = None
    funcs = {}
    code_refs_table = []
    ind = []
    caller_hits = 0
    off = 0
    prev_int3 = False
    while off < n:
        ins = next(md.disasm(data[off:off + 16], lo + off), None)
        if ins is None:
            off += 1
            prev_int3 = False
            continue
        is_int3 = ins.mnemonic == "int3"
        if prev_int3 and not is_int3:
            func = ins.address
        prev_int3 = is_int3
        if func is not None:
            f = funcs.setdefault(func, {"t": 0, "g1": 0, "flag": 0, "ind": []})
        for op in ins.operands:
            if op.type != X86_OP_MEM:
                continue
            if op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
            elif op.mem.base == X86_REG_INVALID and op.mem.index == X86_REG_INVALID:
                tgt = op.mem.disp
            else:
                tgt = None
            if tgt is None:
                continue
            if start <= tgt < end:
                code_refs_table.append((ins.address, ins.mnemonic, ins.op_str, tgt))
            if func is not None:
                if T_RANGE[0] <= tgt < T_RANGE[1]:
                    f["t"] += 1
                if tgt == G1:
                    f["g1"] += 1
                if tgt == FLAG_CELL:
                    f["flag"] += 1
        if func is not None and ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_MEM:
            m = ins.operands[0].mem
            if m.base != X86_REG_INVALID and m.base != X86_REG_RIP and m.index == X86_REG_INVALID:
                f["ind"].append((ins.address, m.disp))
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            if ins.operands[0].imm == CALLER:
                caller_hits += 1
        off += ins.size
    print(f"code refs into table: {[(hex(a), m, o, hex(t)) for a, m, o, t in code_refs_table]}")
    print(f"direct call sites of {hex(CALLER)} (any function): {caller_hits}")

    for off_v in OFFSETS:
        cand = [(a, f) for f, v in funcs.items() for a, d in v["ind"] if d == off_v]
        touch = [(a, f, funcs[f]) for a, f in cand]
        t_hit = [x for x in touch if x[2]["t"] or x[2]["g1"] or x[2]["flag"]]
        print(f"indirect call [reg+{hex(off_v)}]: {len(cand)} sites, "
              f"in functions touching T/G1/flag: {len(t_hit)}")
        for a, f, v in t_hit:
            print(f"  {hex(a)} in {hex(f)} t={v['t']} g1={v['g1']} flag={v['flag']}")
    if mutate:
        print("mutate: table entry changed on purpose")
    print("table.check " + ("PASS" if ok_table else "FAIL"))
    sys.exit(0 if ok_table else 1)


if __name__ == "__main__":
    main()
