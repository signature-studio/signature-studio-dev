#!/usr/bin/env python3
"""dis.py VA... : PE の関数 (.pdata 区間) を capstone で逆アセンブルして表示 (#130)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ldfix'))
import capstone
from ldmach import Machine
PE = os.environ.get('LD_M11_PE', '/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin')
m = Machine(PE)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = False
for a in sys.argv[1:]:
    va = int(a, 16); rva, size = m.fns[va]
    print('== function_%x size=%d' % (va, size))
    for i in cs.disasm(m.read(rva, size), va): print('  %x: %s %s' % (i.address, i.mnemonic, i.op_str))
