#!/usr/bin/env python3
"""根 VA の直接 call 閉包 (深さ N) で、メモリ書込み先と間接 call 箇所を分類して列挙する (PY-5386 / #5765)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_closure_writes_5386.py <根 VA(16進)> [深さ]

閉包の定義は pe_callgraph.py の fwd と同じ (E8 rel32 だけで前進・間接 call は辿らない・深さ上限)。
書込み先の分類 (dest オペランドがメモリのとき):
  rip  : [rip + disp] の絶対アドレス (グローバル)。VA を計算して出す。
  stk  : [rbp/rsp + disp] (関数ローカル)。副作用ではない。
  ptr  : それ以外 (レジスタ経由のポインタ書込み。静的に先が決まらない)。
間接 call: call reg / call [mem] は未解決の枝として箇所数と分類を出す。
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
    __slots__ = ("address", "size", "mnemonic", "op_str", "call_imm", "call_kind", "dest")

    def __init__(self, ins):
        self.address = ins.address
        self.size = ins.size
        self.mnemonic = ins.mnemonic
        self.op_str = ins.op_str
        self.call_imm = None
        self.call_kind = None
        self.dest = None
        if ins.mnemonic == "call" and ins.operands:
            op = ins.operands[0]
            if op.type == capstone.x86.X86_OP_IMM:
                self.call_imm = op.imm
            else:
                self.call_kind = "reg" if op.type == capstone.x86.X86_OP_REG else "mem"
        if ins.mnemonic in WRITE_OPS and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_MEM:
            m = ins.operands[0].mem
            if m.base == capstone.x86.X86_REG_RIP:
                self.dest = ("rip", ins.address + ins.size + m.disp)
            elif m.base in (capstone.x86.X86_REG_RBP, capstone.x86.X86_REG_RSP):
                self.dest = ("stk", None)
            else:
                self.dest = ("ptr", None)


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
        insns.append(Ins(ins))
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
    by_func = collections.defaultdict(list)
    for ins in insns:
        f = func_of(ins.address)
        if f in closure:
            by_func[f].append(ins)

    rip_writes = collections.defaultdict(list)
    kinds = collections.Counter()
    indirect_sites = []
    for f in sorted(closure):
        for ins in by_func.get(f, []):
            if ins.call_kind is not None:
                indirect_sites.append((f, ins.address, ins.call_kind, ins.op_str))
                kinds["indirect_" + ins.call_kind] += 1
            if ins.dest is None:
                continue
            kind, target = ins.dest
            if kind == "rip":
                rip_writes[target].append((f, ins.address, ins.mnemonic, ins.op_str))
            kinds["write_" + kind] += 1

    print(f"root {hex(root)} depth<={depth_max}")
    print(f"closure funcs {len(closure)}")
    print(f"indirect call sites in closure {len(indirect_sites)}")
    print("kinds " + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print("")
    print("## RIP-relative writes (target VA <- writing site)")
    for target in sorted(rip_writes):
        for f, a, m, o in rip_writes[target]:
            print(f"{hex(target)} <- {hex(a)} in {hex(f)}: {m} {o}")
    print("")
    print("## indirect call sites (func, site, kind, operand)")
    for f, a, kind, o in indirect_sites:
        print(f"{hex(f)} {hex(a)} {kind} {o}")


if __name__ == "__main__":
    main()
