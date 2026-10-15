#!/usr/bin/env python3
"""PY-264 (#3888) 受入 2: vptr 候補 0xed0bb0 (表 A)・0xed0c28 (表 B) が、算術で作られて格納される経路の有無を数える。

  FL_WIN64_DIR=<展開先> python3 analysis/py264_arith_scan.py [block名の部分一致]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*_PE.bin'
検査 (直線区間の定数伝播。call・ret・jmp で打ち切り、未知の書込みで値を捨てる):
  - 定数の源: lea reg,[rip+X] / mov reg,imm / mov reg,reg / lea reg,[reg+imm] / add,sub reg,imm。
  - 候補値 (0xed0bb0 / 0xed0c28) に一致する値を持つレジスタを、qword のメモリ格納 (mov [..], reg) の源にする箇所を列挙する。
出力: 格納箇所 1 件ごとに、命令・候補値・源の由来。
限界: 関数をまたぐ値・メモリ経由の値は追わない。結果 0 件は『直線区間の算術では作られない』まで。
"""
import glob
import os
import sys
import time

import capstone
import pefile

EXT = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
CAND = {0xED0BB0: "A", 0xED0C28: "B"}
CHUNK = 1 << 16
MASK = 0xFFFFFFFFFFFFFFFF
X86 = capstone.x86


def family(name):
    for full, names in (
        ("rax", ("rax", "eax", "ax", "al", "ah")),
        ("rbx", ("rbx", "ebx", "bx", "bl", "bh")),
        ("rcx", ("rcx", "ecx", "cx", "cl", "ch")),
        ("rdx", ("rdx", "edx", "dx", "dl", "dh")),
        ("rsi", ("rsi", "esi", "si", "sil")),
        ("rdi", ("rdi", "edi", "di", "dil")),
        ("rbp", ("rbp", "ebp", "bp", "bpl")),
        ("rsp", ("rsp", "esp", "sp", "spl")),
    ):
        if name in names:
            return full
    return name


def scan_block(path, md):
    raw = open(path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    hits, n_ins = [], 0
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        val = {}
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                ops = ins.operands
                m = ins.mnemonic
                if m in ("call", "ret", "jmp"):
                    val.clear()
                    continue
                if m == "mov" and len(ops) == 2 and ops[0].type == X86.X86_OP_MEM \
                        and ops[1].type == X86.X86_OP_REG and ops[0].size == 8:
                    src = family(ins.reg_name(ops[1].reg))
                    if src in val and val[src] in CAND:
                        hits.append((path, ins.address, ins.op_str, val[src]))
                    continue
                if not ops or ops[0].type != X86.X86_OP_REG:
                    continue
                dst = family(ins.reg_name(ops[0].reg))
                if m == "lea" and ops[1].type == X86.X86_OP_MEM:
                    mem = ops[1].mem
                    if mem.base == X86.X86_REG_RIP and mem.index == 0:
                        val[dst] = (ins.address + ins.size + mem.disp) & MASK
                    elif mem.index == 0 and mem.base != 0 and family(ins.reg_name(mem.base)) in val:
                        val[dst] = (val[family(ins.reg_name(mem.base))] + mem.disp) & MASK
                    else:
                        val.pop(dst, None)
                    continue
                if m == "mov" and len(ops) == 2 and ops[1].type == X86.X86_OP_IMM:
                    val[dst] = ops[1].imm & MASK
                    continue
                if m == "mov" and len(ops) == 2 and ops[1].type == X86.X86_OP_REG:
                    s2 = family(ins.reg_name(ops[1].reg))
                    if s2 in val:
                        val[dst] = val[s2]
                    else:
                        val.pop(dst, None)
                    continue
                if m in ("add", "sub") and len(ops) == 2 and ops[1].type == X86.X86_OP_IMM and dst in val:
                    d = ops[1].imm if m == "add" else -ops[1].imm
                    val[dst] = (val[dst] + d) & MASK
                    continue
                if m not in ("cmp", "test", "push"):
                    val.pop(dst, None)
            off = end if end > off else off + 1
    return hits, n_ins


def main():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:
        CAND.clear()
        CAND.update({int(x, 16): x for x in sys.argv[2:]})
    t0 = time.time()
    total_ins, all_hits, n_blocks = 0, [], 0
    for f in sorted(glob.glob(os.path.join(EXT, "*_PE.bin"))):
        if flt not in os.path.basename(f) or open(f, "rb").read(2) != b"MZ":
            continue
        n_blocks += 1
        h, n = scan_block(f, md)
        total_ins += n
        all_hits.extend(h)
    for path, addr, op, v in all_hits:
        print("%s 0x%x mov [..], %s  src=0x%x (vptr %s)" % (os.path.basename(path), addr, op, v, CAND[v]))
    print("blocks=%d instructions=%d hits=%d sec=%.1f" % (n_blocks, total_ins, len(all_hits), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
