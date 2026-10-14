#!/usr/bin/env python3
"""PY-71 (#2501): vtable の各スロットの関数本体で、指定フィールド (disp) を触るメモリ命令を数える (実機不要)。

  python3 analysis/py71_vtable.py <PE.bin> <vtable VA hex> <field disp hex>[,...] [max_slots]

- vtable: 先頭から .text を指す 8 バイトを連続して読む (値が .text 外になるまで。最大 max_slots 件)。
- 各スロットの関数本体は、先頭から int3 パディングまで (最大 0x2000 バイト) を線形に逆アセンブルする。
- 命令のメモリオペランドの disp が指定フィールドと一致したものを数える (ベースレジスタは問わない)。
  ベースを特定しないため、別オブジェクトの同 disp を拾う可能性がある (近似。REPORT で明記)。
"""
import struct
import sys

import capstone
import pefile

path = sys.argv[1]
vt = int(sys.argv[2], 0)
fields = [int(v, 0) for v in sys.argv[3].split(",")]
max_slots = int(sys.argv[4], 0) if len(sys.argv) > 4 else 256
X = capstone.x86

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
tend = tbase + text.Misc_VirtualSize
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def q(va):
    return struct.unpack_from("<Q", data, va - tbase + text.PointerToRawData)[0]


def body(fn):
    off = fn - tbase
    out = []
    while off < len(tdata) and off - (fn - tbase) < 0x2000:
        ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
        if ins is None or ins.mnemonic == "int3":
            break
        out.append(ins)
        off += ins.size
    return out


slots = []
va = vt
while len(slots) < max_slots:
    v = q(va)
    if not (tbase <= v < tend):
        break
    slots.append((va, v))
    va += 8
print(f"# vtable {vt:#x}: {len(slots)} slot(s) (text pointers), end at {va:#x}")
totals = {f: 0 for f in fields}
for i, (sva, fn) in enumerate(slots):
    hits = {f: 0 for f in fields}
    for ins in body(fn):
        for op in ins.operands:
            if op.type == X.X86_OP_MEM and op.mem.disp in hits and op.mem.base != X.X86_REG_RIP:
                hits[op.mem.disp] += 1
    for f in fields:
        totals[f] += 1 if hits[f] else 0
    desc = " ".join(f"{f:#x}:{hits[f]}" for f in fields)
    print(f"slot[{i:3d}] {sva:#x} -> {fn:#x}  {desc}")
print("# slots touching each field (count of slots, not instructions):")
for f in fields:
    print(f"#   disp {f:#x}: {totals[f]} / {len(slots)} slot(s)")
