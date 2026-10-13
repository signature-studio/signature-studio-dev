#!/usr/bin/env python3
"""MSVC C++ engine DLL の .pdata 関数のうち、アドレス順で連続する窓を RetDec --select-ranges 形式 (VA) で出力する。
usage: engine_window.py <block> <start_index> <count>   → stdout: 0xA-0xB,...  (stderr: 総 .pdata 関数数 / 窓の関数数 / バイト数)
"""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
blk, s0, cnt = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % blk), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
data = pd.get_data()[:pd.Misc_VirtualSize]
fs = []
for i in range(len(data) // 12):
    b, e, u = struct.unpack_from('<III', data, 12 * i)
    if b and not (u & 1) and e > b:
        fs.append((b, e))
fs.sort()
w = fs[s0:s0 + cnt]
print(','.join('0x%x-0x%x' % (base + b, base + e - 1) for b, e in w))
print('%d total / %d in window / %d bytes' % (len(fs), len(w), sum(e - b for b, e in w)), file=sys.stderr)
