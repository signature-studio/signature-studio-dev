#!/usr/bin/env python3
"""MSVC C++ engine DLL の全 .pdata 関数を RetDec --select-ranges 形式 (VA) で出力する。
usage: engine_ranges.py <block>   → stdout: 0xA-0xB,...  (stderr: 関数数 / バイト数)
"""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % int(sys.argv[1])), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
data = pd.get_data()[:pd.Misc_VirtualSize]
rs, nb = [], 0
for i in range(len(data) // 12):
    b, e, u = struct.unpack_from('<III', data, 12 * i)
    if b and not (u & 1) and e > b:
        rs.append('0x%x-0x%x' % (base + b, base + e - 1))
        nb += e - b
print(','.join(rs))
print('%d funcs / %d bytes' % (len(rs), nb), file=sys.stderr)
