#!/usr/bin/env python3
# callee_449550_5648.py: #5648 (LD-281) 449550 の呼び先 412d60・413480 の副作用を機械語から確認する。
# 使い方: python3 callee_449550_5648.py <block00031_PE.bin>
# 出力: 各関数の direct call / indirect call / issue のフラグ (0x11cb0c4・0x11cb024) への RIP 相対参照、
#       および 449550 が arg4 == NULL 枝で渡す static 文字列の参照数 (ptr-8) と長さ (ptr-4)。
import sys
import capstone
import pefile

FLAGS = {0x11cb0c4, 0x11cb024}
FUNCS = [0x449550, 0x412d60, 0x413480, 0x409440, 0x407e20, 0x4073e0, 0x4074d0, 0x40802e, 0x40801f]
STATIC = 0x4495f4  # 449550 の 0x44958c 枝 (lea rdx,[rip+0x5d] at 0x449590)

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def body(va):
    out = []
    for i in md.disasm(pe.get_data(va - base, 0x200), va):
        if i.mnemonic == 'int3':
            break
        out.append(i)
    return out


for fn in FUNCS:
    ins = body(fn)
    direct = [hex(i.operands[0].imm) for i in ins
              if i.mnemonic == 'call' and i.operands and i.operands[0].type == capstone.x86.X86_OP_IMM]
    indirect = [i.op_str for i in ins
                if i.mnemonic == 'call' and not (i.operands and i.operands[0].type == capstone.x86.X86_OP_IMM)]
    flags = [hex(i.address) for i in ins for op in i.operands
             if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP
             and i.address + i.size + op.mem.disp in FLAGS]
    print('== %s: direct call=%s indirect call=%s issue-flag refs=%s'
          % (hex(fn), direct, indirect, flags or 'none'))

refcnt = int.from_bytes(pe.get_data(STATIC - 8 - base, 4), 'little', signed=True)
length = int.from_bytes(pe.get_data(STATIC - 4 - base, 4), 'little')
print('static %s refcount(ptr-8)=%d length(ptr-4)=%d' % (hex(STATIC), refcnt, length))
