#!/usr/bin/env python3
"""PY-394 (#4842): G1 (0x15d51a0) の書込み元を、ポインタ格納セル 0x15e4018 の読出しのそれぞれから列挙する。

  FL_WIN64_DIR=<展開先> python3 analysis/py394_g1_cell_reads.py

方式:
- 読出し: `mov reg, [rip+..]` で 0x15e4018 を読むもの (件数を数える)。
- 追跡: 読出しの直後から制御フローグラフ (fall-through・条件/無条件 jmp の直接先) を辿り、
  その値 (= &G1) を持つレジスタの集合を保つ。mov/lea/movsxd/movzx による別名は伝播し、
  他の書込みで上書きされたレジスタは外す。ret で止まる。
- 書込み: 追跡中のレジスタを基底にした `[reg+disp]` への書込みを記録する。G1 は 4 byte の dword
  なので、`-size < disp < 4` のものを G1 への書込みとする。
- 呼出し: 追跡中のレジスタを引数 (rcx/rdx/r8/r9) として直接 call に渡すとき、その call 先を
  深さ MAX_DEPTH まで同じ方式で辿る。間接 call / 解決できない jmp は「未追跡」として数える。
- 近似: レジスタの値の流れだけを見る。メモリ経由の退避・再格納は追わない。
"""
import os
import sys
from collections import namedtuple

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G1 = 0x15D51A0
CELL = 0x15E4018
MAX_DEPTH = int(os.environ.get("PY394_DEPTH", "2"))
STEP_LIMIT = 20000
ARGS = {"rcx", "rdx", "r8", "r9"}
CALLER_SAVED = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
WRITE = {"mov", "movsxd", "movzx", "movsx", "sub", "add", "inc", "dec", "and", "or", "xor", "neg", "not", "xchg", "shl", "shr", "sar", "rol", "ror", "adc", "sbb"}
NONWRITE = {"cmp", "test", "push", "bt"}
COPY = {"mov", "lea", "movsxd", "movzx", "movsx"}

Ins = namedtuple("Ins", "address size mnemonic op_str ops")
Op = namedtuple("Op", "kind reg base disp index imm size")


def canon(name):
    if name is None:
        return None
    m = {}
    for b in ["ax", "bx", "cx", "dx"]:
        m["e" + b] = m[b] = m[b[0] + "l"] = m[b[0] + "h"] = "r" + b
    for b in ["si", "di", "sp", "bp"]:
        m["e" + b] = m[b] = m[b + "l"] = "r" + b
    for i in range(8, 16):
        m[f"r{i}d"] = m[f"r{i}w"] = m[f"r{i}b"] = f"r{i}"
    return m.get(name, name)


def load(md):
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    insns = []
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        ops = []
        for o in ins.operands:
            if o.type == X86_OP_REG:
                ops.append(Op("reg", canon(ins.reg_name(o.reg)), None, 0, None, None, o.size))
            elif o.type == X86_OP_IMM:
                ops.append(Op("imm", None, None, 0, None, o.imm, o.size))
            elif o.type == X86_OP_MEM:
                ops.append(Op("mem", None, canon(ins.reg_name(o.mem.base)) if o.mem.base else None,
                              o.mem.disp, canon(ins.reg_name(o.mem.index)) if o.mem.index else None, None, o.size))
        insns.append(Ins(ins.address, ins.size, ins.mnemonic, ins.op_str, tuple(ops)))
        off += ins.size
    return insns, va0, va0 + n, pe


def rip_target(ins, op):
    return ins.address + ins.size + op.disp


def walk(insns, by_addr, text_lo, text_hi, start, tracked0):
    stores, calls, unresolved = {}, {}, []
    stack = [(start, frozenset(tracked0))]
    seen = set()
    steps = 0
    while stack and steps < STEP_LIMIT:
        idx, tr = stack.pop()
        if not tr or (idx, tr) in seen or idx >= len(insns):
            continue
        seen.add((idx, tr))
        steps += 1
        ins = insns[idx]
        mn = ins.mnemonic
        ops = ins.ops
        if mn in ("ret", "retf"):
            continue
        if ops and ops[0].kind == "mem" and ops[0].base in tr and mn not in NONWRITE and mn != "lea":
            if mn in WRITE and ops[0].index is None:
                stores[ins.address] = (ops[0].disp, ops[0].size, f"{mn} {ins.op_str}")
            else:
                unresolved.append((ins.address, "memdst-not-modelled " + ins.op_str))
        if mn == "call":
            if ops and ops[0].kind == "imm" and text_lo <= ops[0].imm < text_hi:
                calls[ins.address] = (ops[0].imm, sorted(a for a in ARGS if a in tr))
            else:
                unresolved.append((ins.address, ins.op_str))
            tr2 = frozenset(t for t in tr if t not in CALLER_SAVED)
            if tr2 and idx + 1 < len(insns):
                stack.append((idx + 1, tr2))
            continue
        if mn == "jmp":
            if ops and ops[0].kind == "imm" and ops[0].imm in by_addr:
                stack.append((by_addr[ops[0].imm], tr))
            else:
                unresolved.append((ins.address, ins.op_str))
            continue
        if mn.startswith("j"):
            if ops and ops[0].kind == "imm" and ops[0].imm in by_addr:
                stack.append((by_addr[ops[0].imm], tr))
            if idx + 1 < len(insns):
                stack.append((idx + 1, tr))
            continue
        if len(ops) == 2 and mn == "mov" and ops[0].kind == "mem" and ops[0].base not in tr and ops[1].kind == "reg" and ops[1].reg in tr:
            unresolved.append((ins.address, "spill " + ins.op_str))
        nt = set(tr)
        if ops and ops[0].kind == "reg" and mn not in NONWRITE:
            dst = ops[0].reg
            src_in = len(ops) > 1 and (
                (ops[1].kind == "reg" and ops[1].reg in tr)
                or (ops[1].kind == "mem" and mn == "lea" and ops[1].base in tr)
            )
            if src_in and mn in COPY:
                nt.add(dst)
            else:
                nt.discard(dst)
        nt = frozenset(nt)
        if nt and idx + 1 < len(insns):
            stack.append((idx + 1, nt))
    return stores, calls, unresolved, steps


def main():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    insns, text_lo, text_hi, pe = load(md)
    by_addr = {ins.address: i for i, ins in enumerate(insns)}
    raw = open(PE, "rb").read()

    reads = []
    cell_writes = []
    cell_other = []
    for i, ins in enumerate(insns):
        for k, op in enumerate(ins.ops):
            if op.kind != "mem" or op.base != "rip" or rip_target(ins, op) != CELL:
                continue
            if ins.mnemonic == "mov" and k == 1 and ins.ops[0].kind == "reg":
                reads.append((i, ins.ops[0].reg))
            elif ins.mnemonic in WRITE and k == 0:
                cell_writes.append((ins.address, ins.mnemonic + " " + ins.op_str))
            else:
                cell_other.append((ins.address, ins.mnemonic + " " + ins.op_str))
    abs_count = raw.count(CELL.to_bytes(8, "little"))

    print(f"reads of cell {CELL:#x} (mov reg, [rip+..]): {len(reads)}")
    print(f"writes to cell {CELL:#x}: {len(cell_writes)}")
    for a, s in cell_writes:
        print(f"  {a:#x}  {s}")
    print(f"other RIP-relative refs to cell: {len(cell_other)}")
    for a, s in cell_other:
        print(f"  {a:#x}  {s}")
    print(f"8-byte absolute occurrences of cell address in file: {abs_count}")

    total_steps = 0
    unresolved_total = 0
    per_read = []
    for i, reg in reads:
        origin = insns[i].address
        stores_all = {}
        calls_all = {}
        todo = [(i + 1, frozenset({reg}), 0)]
        done = set()
        while todo:
            start, tr, depth = todo.pop()
            if (start, tr, depth) in done or start >= len(insns):
                continue
            done.add((start, tr, depth))
            st, cl, un, steps = walk(insns, by_addr, text_lo, text_hi, start, tr)
            total_steps += steps
            unresolved_total += len(un)
            for a, v in st.items():
                stores_all.setdefault(a, v)
            for site, (tgt, args) in cl.items():
                calls_all[site] = (tgt, args, depth)
                if depth < MAX_DEPTH and tgt in by_addr:
                    for a in args:
                        todo.append((by_addr[tgt], frozenset({a}), depth + 1))
        per_read.append((origin, stores_all, calls_all))

    g1_stores = {}
    other_stores = {}
    for origin, stores_all, _ in per_read:
        for a, v in stores_all.items():
            disp, size, text = v
            bucket = g1_stores if -size < disp < 4 else other_stores
            bucket.setdefault(a, [v, set()])[1].add(origin)
    with_call = sum(1 for _, _, c in per_read if c)
    nopath = sum(1 for _, s, c in per_read if not s and not c)
    print(f"reads with at least one direct call on the tracked path: {with_call}")
    print(f"reads with no store and no call on any path: {nopath}")
    print(f"unresolved transfers and non-modelled memory destinations seen: {unresolved_total}")
    print(f"total walk steps: {total_steps}")
    print(f"G1 store sites through the loaded pointer: {len(g1_stores)}")
    for a in sorted(g1_stores):
        (disp, size, text), rs = g1_stores[a]
        print(f"  {a:#x}  disp={disp} size={size}  {text}  read {', '.join(hex(x) for x in sorted(rs))}")
    print(f"store sites through the loaded pointer, disp outside G1: {len(other_stores)}")
    for a in sorted(other_stores)[:200]:
        (disp, size, text), rs = other_stores[a]
        print(f"  {a:#x}  disp={disp} size={size}  {text}  reads={len(rs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
