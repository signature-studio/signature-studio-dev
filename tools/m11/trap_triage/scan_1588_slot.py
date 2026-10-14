#!/usr/bin/env python3
# #1588: 410320 の間接 call (call [rax-0x30]) が読むスロットへの参照を PE .text から静的に探す。
#   usage: LD_M11_PE=<block00031_PE.bin> python3 scan_1588_slot.py
#   出力: [rip+disp] で対象 VA を指す命令 / 即値で対象 VA を持つ命令 (直接参照のみ。間接書き込みは見えない)。
import os
import capstone

PE = os.environ.get('LD_M11_PE', 'block00031_PE.bin')
IB = 0x400000
TEXT_RAW, TEXT_VA, TEXT_SZ = 0x400, 0x1000, 0xfa34b0
TARGETS = {0x5ac308, 0x5ac338, 0x409410, 0x40f960, 0x5af3d0}

with open(PE, 'rb') as f:
    code = f.read()[TEXT_RAW:TEXT_RAW + TEXT_SZ]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
hits = []
for ins in md.disasm(code, IB + TEXT_VA):
    s = ins.op_str
    if '[rip' in s:
        disp = s.split('[rip')[1].split(']')[0].replace(' ', '')
        d = int(disp[1:], 16) * (1 if disp[0] == '+' else -1)
        t = ins.address + ins.size + d
        if t in TARGETS or t - IB in TARGETS:
            hits.append((hex(ins.address), ins.mnemonic, s, 'rip->' + hex(t)))
        continue
    for tok in s.replace('[', ' ').replace(']', ' ').replace(',', ' ').split():
        try:
            v = int(tok, 16)
        except ValueError:
            continue
        if v in TARGETS or v - IB in TARGETS:
            hits.append((hex(ins.address), ins.mnemonic, s))
            break
for h in hits:
    print(*h)
print('total', len(hits))
