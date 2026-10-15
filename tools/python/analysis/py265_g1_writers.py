#!/usr/bin/env python3
"""PY-265 (#3889): G1 (0x15d51a0) の書込み元を、RIP 相対 (直接) と、ポインタ格納セル 0x15e4018 経由 (間接) の両方で列挙する。

  FL_WIN64_DIR=<展開先> python3 analysis/py265_g1_writers.py

- 直接: G1 を指す RIP 相対オペランドのうち、先頭オペランドがメモリで、命令が書込み (mov/sub/add/inc/dec/and/or/xor/mov の先頭が [rip+..]) のもの。
- 間接: セル 0x15e4018 を RIP 相対で読み (mov reg, [rip+..])、その reg を基底にしたメモリ先頭オペランド ([reg] / [reg+disp]) で書込みを行う命令。
  同一関数内 (直前 CHAIN 命令以内で reg が上書きされるまで) だけを見る。レジスタの追跡は直線の近似で、分岐越えは追わない。
  G1 への書込みかどうかは disp と読込み元の対応では判定できないため、候補として出し、目視で確認する。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G1 = 0x15D51A0
CELL = 0x15E4018
CHAIN = 12
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
MEM_DST = re.compile(r"^(mov|movsxd|sub|add|inc|dec|and|or|xor|neg|not|xchg)\s+(?:byte|word|dword|qword) ptr \[([a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]")
WRITE_RIP = re.compile(r"^(mov|sub|add|inc|dec|and|or|xor|neg|not)\s+(?:byte|word|dword|qword) ptr \[rip ([+-]) (0x[0-9a-f]+)\]")


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    insns = []
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        insns.append(ins)
        off += ins.size
    return insns


def main():
    insns = load()
    direct = []
    indirect = []
    for i, ins in enumerate(insns):
        m = WRITE_RIP.search(f"{ins.mnemonic} {ins.op_str}")
        if m:
            d = int(m.group(3), 16) * (1 if m.group(2) == "+" else -1)
            if ins.address + ins.size + d == G1:
                direct.append((ins.address, f"{ins.mnemonic} {ins.op_str}"))
        if ins.mnemonic == "mov" and "[rip" in ins.op_str and ins.op_str.split(",")[0].strip() in {r for r in ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]}:
            mm = RIP.search(ins.op_str)
            if mm:
                d = int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
                if ins.address + ins.size + d == CELL:
                    reg = ins.op_str.split(",")[0].strip()
                    for j in range(i + 1, min(i + 1 + CHAIN, len(insns))):
                        nxt = insns[j]
                        if nxt.mnemonic in ("ret", "call", "jmp") or nxt.mnemonic.startswith("j"):
                            break
                        mw = MEM_DST.search(f"{nxt.mnemonic} {nxt.op_str}")
                        if mw and mw.group(2) == reg and nxt.mnemonic not in ("lea",):
                            indirect.append((ins.address, nxt.address, f"{nxt.mnemonic} {nxt.op_str}"))
                        if nxt.op_str.startswith(reg + ",") or nxt.op_str.startswith(reg + " ,"):
                            break
    print(f"direct G1 writes (RIP-relative): {len(direct)}")
    for a, s in direct:
        print(f"  {a:#x}  {s}")
    print(f"indirect candidates via cell {CELL:#x} (reg-based store within {CHAIN} insns): {len(indirect)}")
    for a, b, s in indirect:
        print(f"  load {a:#x} -> store {b:#x}  {s}")


if __name__ == "__main__":
    main()
