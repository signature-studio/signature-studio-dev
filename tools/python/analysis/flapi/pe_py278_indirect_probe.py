#!/usr/bin/env python3
"""#3965 (PY-278): 0xfff070・0xd1af20・0x1262970 の間接呼出し経路を探す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py278_indirect_probe.py

- rip: [rip+disp] / lea で指す先が対象 VA (または関数ポインタ表の範囲) の命令を全て出す。
- abs: 命令の即値・disp32 に対象 VA が現れる箇所を出す。
- raw: PE ファイル全体 (.data・.rdata・.reloc 含む) で、対象 VA を 8 byte LE で格納する位置を出す。
"""
import bisect
import collections
import os
import struct
import sys

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph  # noqa: E402

PE = pe_callgraph.PE
TABLE_LO, TABLE_HI = 0xfe2c80, 0xfe2ea0
TARGETS = [0xfff070, 0xd1af20, 0x1262970, 0x125b1c0]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    tset = set(TARGETS)

    print("== rip: [rip+disp] の参照先 (対象 VA と表の範囲)")
    rip_hits = collections.defaultdict(list)
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in tset or TABLE_LO <= tgt <= TABLE_HI:
                    rip_hits[tgt].append((ins.address, ins.mnemonic, ins.op_str))
    for tgt in sorted(rip_hits):
        for a, m, o in rip_hits[tgt]:
            print(f"  {hex(tgt)} <- {hex(a)} {m} {o}")

    print("== abs: 即値・disp に対象 VA が現れる箇所 (表の範囲を含む)")
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        for op in ins.operands:
            vals = []
            if op.type == capstone.x86.X86_OP_IMM:
                vals.append(op.imm & 0xffffffffffffffff)
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                vals.append(op.mem.disp & 0xffffffffffffffff)
            for v in vals:
                if v in tset or TABLE_LO <= v <= TABLE_HI or (v - 0x400000) in tset:
                    print(f"  {hex(ins.address)} {ins.mnemonic} {ins.op_str}")

    print("== raw: PE 全体で 8 byte LE として対象 VA を格納する位置 (RVA と section)")
    for v in sorted(tset):
        pat = struct.pack("<Q", v)
        pos = raw.find(pat)
        hits = []
        while pos != -1:
            hits.append(pos)
            pos = raw.find(pat, pos + 1)
        secs = []
        for h in hits:
            name = "?"
            for s in pe.sections:
                if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData:
                    name = s.Name.rstrip(b"\0").decode()
                    rva = s.VirtualAddress + (h - s.PointerToRawData)
                    secs.append(f"{name}+{hex(rva)}")
                    break
            else:
                secs.append(f"file+{hex(h)}")
        print(f"  {hex(v)}: {len(hits)} hit(s) {secs}")


if __name__ == "__main__":
    main()
