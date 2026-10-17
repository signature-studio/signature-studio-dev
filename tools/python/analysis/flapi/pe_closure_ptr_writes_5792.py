#!/usr/bin/env python3
"""根 VA の直接 call 閉包 (深さ N) 内の `[reg+disp]` 書込み箇所を全件 TSV で列挙する (PY-5389 / #5792)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_closure_ptr_writes_5792.py <根 VA(16進)> [深さ] > out.tsv

閉包の定義は pe_closure_writes_5386.py と同じ (E8 rel32 だけで前進・間接 call は辿らない・深さ上限)。
書込み先アドレスは静的に決まらないため、列 target は全件「未確認 (実行時 object 状態)」。
列 dead_suspect は、関数内で ret/無条件 jmp の直後から、次に分岐先になる命令までの区間に入るか
(ret 後のデータ領域を命令として読んだ誤逆アセンブルの疑い)。ヒューリスティックで、除外はしない。
"""
import bisect
import collections
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
WRITE_OPS = {"mov", "add", "sub", "or", "and", "xor", "inc", "dec", "neg", "not",
             "shl", "shr", "sar", "adc", "sbb", "rol", "ror", "setne", "sete", "setg",
             "setl", "setge", "setle", "seta", "setb", "setae", "setbe", "setz", "setnz"}


class Ins:
    __slots__ = ("address", "size", "mnemonic", "op_str", "call_imm", "call_kind", "ptr", "branch_imm")

    def __init__(self, ins, md):
        self.address = ins.address
        self.size = ins.size
        self.mnemonic = ins.mnemonic
        self.op_str = ins.op_str
        self.call_imm = None
        self.call_kind = None
        self.ptr = None
        self.branch_imm = None
        if ins.mnemonic == "call" and ins.operands:
            op = ins.operands[0]
            if op.type == capstone.x86.X86_OP_IMM:
                self.call_imm = op.imm
            else:
                self.call_kind = "reg" if op.type == capstone.x86.X86_OP_REG else "mem"
        if ins.mnemonic.startswith("j") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            self.branch_imm = ins.operands[0].imm
        if ins.mnemonic in WRITE_OPS and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_MEM:
            m = ins.operands[0].mem
            if m.base not in (0, capstone.x86.X86_REG_RIP, capstone.x86.X86_REG_RBP, capstone.x86.X86_REG_RSP):
                self.ptr = (md.reg_name(m.base), m.disp, m.index != 0)


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    insns = []
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        insns.append(Ins(ins, md))
        off += ins.size
    return insns


def function_starts(insns):
    starts = []
    prev = None
    for ins in insns:
        if prev is not None and prev == "int3" and ins.mnemonic != "int3":
            starts.append(ins.address)
        prev = ins.mnemonic
    return starts


def main():
    root = int(sys.argv[1], 16)
    depth_max = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    insns = load()
    starts = function_starts(insns)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    calls_of = collections.defaultdict(set)
    for ins in insns:
        if ins.call_imm is not None:
            f = func_of(ins.address)
            if f is not None:
                calls_of[f].add(ins.call_imm)

    parent = {root: 0}
    frontier = [root]
    depth = 0
    while frontier and depth < depth_max:
        nxt = []
        for f in frontier:
            for t in sorted(calls_of.get(f, ())):
                if t not in parent:
                    parent[t] = f
                    nxt.append(t)
        frontier = nxt
        depth += 1

    closure = set(parent)
    targets = {ins.branch_imm for ins in insns if ins.branch_imm is not None}
    dead_addrs = set()
    for f in sorted(closure):
        i = bisect.bisect_right(starts, f)
        end = starts[i] if i < len(starts) else 0x7FFFFFFFFFFFFFFF
        in_dead = False
        for ins in insns:
            if not (f <= ins.address < end):
                continue
            if ins.address in targets:
                in_dead = False
            if in_dead:
                dead_addrs.add(ins.address)
            if ins.mnemonic in ("ret", "jmp"):
                in_dead = True

    rows = []
    for ins in insns:
        f = func_of(ins.address)
        if f in closure and ins.ptr is not None:
            rows.append((f, ins))

    print(f"# root {hex(root)} depth<={depth_max} closure_funcs={len(closure)} ptr_writes={len(rows)} "
          f"dead_suspect={sum(1 for _, i in rows if i.address in dead_addrs)}", file=sys.stderr)
    print("func\tsite\tbase\tdisp\tindex\tinsn\ttarget\tdead_suspect")
    for f, ins in rows:
        base, disp, has_idx = ins.ptr
        print(f"{hex(f)}\t{hex(ins.address)}\t{base}\t{disp:#x}\t{int(has_idx)}\t"
              f"{ins.mnemonic} {ins.op_str}\t未確認 (実行時 object 状態)\t{int(ins.address in dead_addrs)}")


if __name__ == "__main__":
    main()
