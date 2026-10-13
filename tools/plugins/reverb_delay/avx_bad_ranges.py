#!/usr/bin/env python3
"""MSVC engine の .text 関数のうち、AVX2/AVX-512 permute 系 mnemonic を含むものを RetDec 除外候補として列挙する。
(REPORT §7 の 78/2,078 の mnemonic 基準の再現。 因果ではなく相関に基づく除外。)
usage: avx_bad_ranges.py <block> > bad.out   (stdout: 0xA-0xB 行。 engine_ranges.py --exclude-ranges に渡す)
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

BAD = {'vpermpd', 'vpermd', 'vpexpandd', 'vshufi32x4', 'valignd'}
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % int(sys.argv[1])), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
data = pd.get_data()[:pd.Misc_VirtualSize]
md = Cs(CS_ARCH_X86, CS_MODE_64)
n = 0
for i in range(len(data) // 12):
    b, e, u = struct.unpack_from('<III', data, 12 * i)
    if not b or (u & 1) or e <= b:
        continue
    sec = [s for s in pe.sections if s.VirtualAddress <= b < s.VirtualAddress + s.Misc_VirtualSize]
    if not sec or sec[0].Name.rstrip(b'\0') != b'.text':
        continue
    ms = {x.mnemonic for x in md.disasm(pe.get_data(b, e - b), base + b)}
    if ms & BAD:
        n += 1
        print('0x%x-0x%x' % (base + b, base + e - 1))
print('bad %d' % n, file=sys.stderr)
