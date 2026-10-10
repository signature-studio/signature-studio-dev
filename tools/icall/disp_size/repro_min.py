#!/usr/bin/env python3
"""repro_min.py — D9 の最小再現 (CAB-229 要件1)。 usage: python3 repro_min.py   (PYTHONPATH で別 capstone を差し替え可能)

capstone の x86 `disp_size` は、REX.W 無しで 0x66 を伴う disp32 メモリ命令 (rip 相対 / [reg+disp32] / [abs32]) で 2 を返す。
VEX2 (C5) の pp=01 (= 66 相当) でも同じ。disp_offset と mem.disp の値は正しい。
"""
import os, sys
import capstone
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dispfix as D

cs = Cs(CS_ARCH_X86, CS_MODE_64)
cs.detail = True
CASES = [
    ('66 0f 2f 05 10 00 00 00',        'comisd xmm0,[rip+0x10]       (66 mandatory prefix)'),
    ('66 01 05 10 00 00 00',           'add [rip+0x10],ax            (66 operand-size)'),
    ('66 c7 05 10 00 00 00 34 12',     'mov word [rip+0x10],0x1234   (imm16 は disp の後)'),
    ('66 8b 80 44 33 22 11',           'mov ax,[rax+disp32]          (rip 以外の disp32)'),
    ('66 8b 84 24 44 33 22 11',        'mov ax,[rsp+disp32]          (SIB)'),
    ('66 8b 04 25 44 33 22 11',        'mov ax,[disp32]              (SIB base 無し)'),
    ('c5 f9 10 05 10 00 00 00',        'vmovupd xmm0,[rip+0x10]      (VEX2 pp=66)'),
    ('66 48 01 05 10 00 00 00',        'add [rip+0x10],rax w/ 66+REX.W (正: capstone も 4)'),
    ('f2 0f 10 05 10 00 00 00',        'movsd xmm0,[rip+0x10]        (F2 は無害)'),
    ('f3 0f 10 05 10 00 00 00',        'movss xmm0,[rip+0x10]        (F3 は無害)'),
    ('01 05 10 00 00 00',              'add [rip+0x10],eax           (無 prefix)'),
    ('c4 e1 79 10 05 10 00 00 00',     'vmovupd (VEX3 pp=66, capstone も 4)'),
    ('66 8b 40 08',                    'mov ax,[rax+8]               (disp8 は正)'),
]
print('capstone.__version__ = %s (module %s)' % (capstone.__version__, os.path.dirname(capstone.__file__)))
print('%-30s %-62s %5s %5s %5s  %s' % ('bytes', 'insn', 'cs_sz', 'cs_of', 'fixed', 'verdict'))
nbad = 0
for hx, desc in CASES:
    ins = next(cs.disasm(bytes.fromhex(hx.replace(' ', '')), 0x1000))
    sp = D.disp_span(ins)
    fixed = (sp[1] if sp else 0)
    bad = ins.disp_size != fixed
    nbad += bad
    print('%-30s %-62s %5d %5d %5d  %s' % (hx, desc, ins.disp_size, ins.disp_offset, fixed, 'D9 (capstone 誤り)' if bad else 'ok'))
print('capstone 誤報告: %d / %d' % (nbad, len(CASES)))
