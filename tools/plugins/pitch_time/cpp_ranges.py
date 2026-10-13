#!/usr/bin/env python3
"""MSVC C++ engine DLL の全 .pdata 関数を RetDec --select-ranges 形式 (VA) で出力する。
usage: cpp_ranges.py <block> [<outprefix> <max_chars>]
  引数 1 個: stdout に全 range (0xA-0xB,...) を 1 行、stderr に「N funcs / M bytes」。
  3 個: range を 1 行 max_chars 以内 (retdec の引数長 = execve の 1 引数上限 131072 B 未満) に分けて <outprefix>.<k>.txt に書き、
        stderr に「N funcs / M bytes / K chunks」。 stdout は空。
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
if len(sys.argv) == 4:
    pre, lim = sys.argv[2], int(sys.argv[3])
    chunks, cur, n = [], [], 0
    for x in rs:
        if cur and n + len(x) + 1 > lim:
            chunks.append(cur); cur, n = [], 0
        cur.append(x); n += len(x) + 1
    chunks.append(cur)
    for k, c in enumerate(chunks):
        open('%s.%d.txt' % (pre, k), 'w').write(','.join(c))
    print('%d funcs / %d bytes / %d chunks' % (len(rs), nb, len(chunks)), file=sys.stderr)
else:
    print(','.join(rs))
    print('%d funcs / %d bytes' % (len(rs), nb), file=sys.stderr)
