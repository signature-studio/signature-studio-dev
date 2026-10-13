#!/usr/bin/env python3
"""12 shell の Gen_Render / TriggerVoice の静的な形 (サイズ・direct/間接 call 数) を TSV で出す。 FL_WIN64_DIR 要。
 サイズは .pdata の BeginAddress/EndAddress。 call 数は capstone の linear disasm (オペランドが即値 = direct)。
"""
import os, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'inventory'))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'shared'))
import win_abi  # noqa: E402
from paths import FL_WIN64_DIR  # noqa: E402

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
for line in open(sys.argv[1]):
    blk, name, _va, _isz = line.rstrip('\n').split('\t')
    fn = 'block%05d_PE.bin' % int(blk)
    d = open(os.path.join(FL_WIN64_DIR, 'extracted', fn), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    pd = {f.struct.BeginAddress + base: f.struct.EndAddress + base for f in pe.DIRECTORY_ENTRY_EXCEPTION}
    impl = win_abi.scan(fn)['impl']
    cols = []
    for k in ('Gen_Render', 'TriggerVoice'):
        va = int(impl[k], 16)
        sz = pd[va] - va
        o = pe.get_offset_from_rva(va - base)
        cd = ci = 0
        for i in md.disasm(d[o:o + sz], va):
            if i.mnemonic == 'call':
                if i.operands[0].type == 2:
                    cd += 1
                else:
                    ci += 1
        cols += [sz, cd, ci]
    print('\t'.join(map(str, [blk, name] + cols)))
