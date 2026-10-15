#!/usr/bin/env python3
# u3_check_4040.py: REPORT_1325 §8 U-3 の機械語確認 (#4040)。
# 修復 11 site ごとに、B の先頭から最初の deref (DEREF) の直前までの命令を逆アセンブルし、
# メモリ書込 (mov/movsq/xchg 等の mem 宛先)・call・lock・rep を数える。
# 使い方: python3 u3_check_4040.py <block00031_PE.bin>
import sys
import capstone
import pefile

SITES = [
    ('40fe90', 0x40fe99, 0x40fe99),
    ('41b8d0', 0x41b8de, 0x41b8de),
    ('41b970', 0x41b97e, 0x41b97e),
    ('449550', 0x44957a, 0x44957e),
    ('44f040', 0x44f062, 0x44f069),
    ('44fb40', 0x44fb6a, 0x44fb71),
    ('47ad70', 0x47ad82, 0x47ad82),
    ('784ed0', 0x784f32, 0x784f36),
    ('806740', 0x806784, 0x80678f),
    ('c40420', 0xc40632, 0xc4065b),
    ('f552a0', 0xf552b4, 0xf552b6),
]

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
for fn, b, deref in SITES:
    code = pe.get_data(b - base, deref - b + 16)
    print('== fn 0x%s B=0x%x deref=0x%x' % (fn, b, deref))
    writes = calls = 0
    for ins in md.disasm(code, b):
        if ins.address >= deref:
            break
        print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
        if ins.mnemonic.startswith('call'):
            calls += 1
        if ins.mnemonic.startswith(('lock', 'rep')):
            writes += 1
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and ins.mnemonic.startswith(('mov', 'xchg', 'and', 'or', 'add', 'sub', 'inc', 'dec')):
                if op.access & capstone.CS_AC_WRITE:
                    writes += 1
    print('  => call=%d write=%d' % (calls, writes))
