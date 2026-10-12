#!/usr/bin/env python3
"""hs_disp_tree.py — CAB-195 検収: FLE Dispatcher (0x13173a0) の ID 分岐追跡 (独立照合)。

hostshim.c は「ID 0x56 の case は 0x131bb5c で global オブジェクトポインタを返す」と
主張する。ここでは Dispatcher 先頭から **ID を具体値として駆動** し (ABI.md §2.3 の
「cmp/sub 連鎖の二分木」)、到達 case 番地を独立に求める。

アルゴリズム (別実装: capstone 線形走査 + ID 具体駆動):
  * 追跡対象レジスタ = eax/rax/r8d/r8 (Host Dispatcher の ID は r8d。mov eax,r8d は
    受け渡しとして式を変えない)。
  * 追跡式 = (a, b) = a*ID + b (a=0 で ID 非依存)。sub eax,N → b-=N / add → b+=N /
     mov eax,IMM → a=0,b=IMM。
  * cmp eax,IMM の時点で a*ID+b を評価し、直後の Ja 系条件ジャンプの成否を確定させる。
これにより hs_hostfix/fw_table を介さない native 側の経路だけで ID→case を確定する。

使い方: python3 hs_disp_tree.py [IDs...]
"""
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_REG

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR, REPO_ROOT
PE = _os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
DISP = 0x13173a0
WANT = [int(a, 0) for a in sys.argv[1:]] or [0x47, 0x56, 0x0d, 0x2e, 0x1d, 0x32, 0x0a]
REGS = ('eax', 'rax', 'r8d', 'r8')

d = open(PE, 'rb').read()
pe = pefile.PE(data=d)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
o = pe.get_offset_from_rva(DISP - base)
CODE = d[o:o + 0x8000]
STEP = {}


def insn(addr):
    if addr not in STEP:
        for i in md.disasm(CODE[addr - DISP:addr - DISP + 16], addr):
            STEP[addr] = i
            break
        else:
            STEP[addr] = None
    return STEP[addr]


def trace(ident):
    a, b, addr, cond, taken = 1, 0, DISP, {}, []
    for k in range(6000):
        i = insn(addr)
        if i is None:
            return addr, 'decode 終端 @0x%x' % addr, k, taken
        mn, ops = i.mnemonic, i.operands
        nxt = i.address + i.size
        if mn == 'jmp' and ops[0].type == X86_OP_IMM:
            addr = ops[0].imm
            continue
        if mn in ('je', 'jne', 'ja', 'jae', 'jb', 'jbe', 'jg', 'jge', 'jl', 'jle') \
           and ops[0].type == X86_OP_IMM:
            tgt = ops[0].imm
            ok = cond.get(mn, False)
            if ok:
                taken.append('%s->0x%x' % (mn, tgt))
            addr = tgt if ok else nxt
            continue
        if mn in ('sub', 'cmp', 'add') and len(ops) == 2 and ops[0].type == X86_OP_REG \
           and i.reg_name(ops[0].reg) in REGS and ops[1].type == X86_OP_IMM:
            v, cur = ops[1].imm, a * ident + b
            if mn == 'sub':
                b -= v
            elif mn == 'add':
                b += v
            else:
                cond = {'je': cur == v, 'jne': cur != v, 'ja': cur > v, 'jae': cur >= v,
                        'jb': cur < v, 'jbe': cur <= v, 'jg': cur > v, 'jge': cur >= v,
                        'jl': cur < v, 'jle': cur <= v}
        elif mn == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_REG \
                and i.reg_name(ops[0].reg) in REGS:
            if ops[1].type == X86_OP_IMM:
                a, b = 0, ops[1].imm
            # mov eax,r8d / mov r8d,eax は ID の受け渡し → 式を変えない
        addr = nxt
    return addr, 'ステップ上限', k, taken


for ident in WANT:
    addr, why, k, taken = trace(ident)
    print('[disp] ID=0x%02x -> case 0x%x (%s, %d steps)' % (ident, addr, why, k))
    print('        採取分岐: %s' % (' -> '.join(taken) if taken else 'なし'))
