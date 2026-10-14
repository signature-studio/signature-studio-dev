#!/usr/bin/env python3
"""PY-67 (#2159): 間接参照の経路を調べる (実機不要)。

  python3 analysis/py67_indirect.py <PE.bin> <target VA hex>[,<target VA hex>...] [near hex]

1. .text を 1 回だけ線形走査し、target (± near) を指す RIP 相対オペランドを出す。
   STORE (書込み先が target 近傍)・lea・load を区別する。
2. ファイル全体で target の絶対値 (8 バイト / 4 バイト) を格納している箇所を出す。
   PE 上の絶対 VA は ImageBase を足さない値 (capstone の出力と同じ)。
3. 線形走査は命令境界がずれることがあるので、採用前に py58_context.py で確認すること。
"""
import struct
import sys

import capstone
import pefile

path = sys.argv[1]
targets = [int(v, 0) for v in sys.argv[2].split(",")]
near = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff = text.PointerToRawData
tsize = text.SizeOfRawData
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
tdata = data[toff:toff + tsize]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
ranges = [(t - near, t + near) for t in targets]

off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        continue
    off += ins.size
    if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
        dst = ins.operands[0].imm
        for t in targets:
            if dst == t:
                print(f"[{t:#x}] {ins.address:#x}: {ins.mnemonic} {dst:#x}  [direct-{ins.mnemonic}]")
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
            for t in targets:
                if op.mem.disp == t:
                    print(f"[{t:#x}] {ins.address:#x}: {ins.mnemonic} {ins.op_str}  [abs-disp]")
        if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
            continue
        tgt = ins.address + ins.size + op.mem.disp
        for t, (lo, hi) in zip(targets, ranges):
            if lo <= tgt <= hi:
                if ins.mnemonic == "lea":
                    kind = "lea"
                elif op.access & capstone.CS_AC_WRITE:
                    kind = "STORE"
                else:
                    kind = "load"
                print(f"[{t:#x}] {ins.address:#x}: {ins.mnemonic} {ins.op_str}  -> {tgt:#x}  [{kind}]")

for t in targets:
    for width, fmt in ((8, "<Q"), (4, "<I")):
        needle = struct.pack(fmt, t)
        pos = data.find(needle)
        hits = []
        while pos != -1:
            hits.append(pos)
            pos = data.find(needle, pos + 1)
        print(f"# [{t:#x}] absolute {width}-byte value: {len(hits)} hit(s)")
        for h in hits[:50]:
            sec = next((s.Name.rstrip(b"\0").decode() for s in pe.sections
                        if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData), "?")
            print(f"#   file offset {h:#x} section={sec}")
