#!/usr/bin/env python3
"""PY-5144 (#5144): 群 C の 2 つの VMT を参照する命令 (コンストラクタ候補) を .text から探す。

  python3 analysis/py5144_ctor.py <PE.bin>

対象 VMT (本体の VA。自己ポインタ値 0xb07378・0xb655c8 ではない): TDBXStreamValue 0xb07308 (受け手 +0x18)・TGenericPlugin 0xb65558 (受け手 +0x7a0)。
見るもの:
  - `mov qword [mem], imm32` (即値が VMT アドレス。符号拡張 imm32 を含む)
  - `lea reg, [rip+disp]` (target が VMT アドレス)
各ヒットについて address・命令を出す (即値を含む全命令を数える。cmp・push 等を含みうる)。
線形走査 (64KiB 単位) の近似で、データ部の誤デコードを含みうる。
"""
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
VMTS = {0xB07308: "TDBXStreamValue", 0xB65558: "TGenericPlugin"}

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tbase = ib + text.VirtualAddress
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
hits = {v: [] for v in VMTS.values()}
pos = 0
while pos < len(tdata):
    end = min(len(tdata), pos + 0x10000)
    for ins in md.disasm(tdata[pos:end], tbase + pos):
        for op in ins.operands:
            if op.type == X.X86_OP_IMM and op.imm in VMTS:
                hits[VMTS[op.imm]].append((ins.address, ins.mnemonic, ins.op_str))
            if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in VMTS and ins.mnemonic == "lea":
                    hits[VMTS[tgt]].append((ins.address, ins.mnemonic, ins.op_str))
    pos = end

for name, lst in hits.items():
    print(f"== {name}: 参照命令 {len(lst)} 件")
    for a, m, s in lst:
        print(f"  {a:#x}  {m} {s}")
