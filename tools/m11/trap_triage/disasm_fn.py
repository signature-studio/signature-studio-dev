#!/usr/bin/env python3
"""disasm_fn.py VA... : PE の関数 (.pdata 区間) を capstone で逆アセンブルして表示 (#130)"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ldfix'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
import capstone
from ldmach import Machine
from paths import FL_WIN64_DIR  # docs/REFERENCES.md [WIN64]
PE = os.environ.get('LD_M11_PE', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')
m = Machine(PE)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = False
for a in sys.argv[1:]:
    va = int(a, 16); rva, size = m.fns[va]
    print('== function_%x size=%d' % (va, size))
    for i in cs.disasm(m.read(rva, size), va): print('  %x: %s %s' % (i.address, i.mnemonic, i.op_str))
