#!/usr/bin/env python3
"""x86_64 Mach-O: rip相対参照 (lea/mov/call) の xref 検索。usage: xref.py slice VA [VA...]"""
import sys, os, struct
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared', 'scripts'))
from macho_util import MachO
def xrefs(m, targets):
    tx = m.section("__TEXT", "__text"); t0, tsz, tva = tx[4], tx[3], tx[2]
    arr = np.frombuffer(m.d, dtype=np.uint8, count=tsz, offset=t0)
    # modrm mod=00 rm=101 → rip+disp32 ; scan every byte where (b&0xC7)==0x05, disp at +1
    pos = np.where((arr[:-4] & 0xC7) == 0x05)[0] + 1
    pos = pos[pos + 4 < len(arr)]
    bb = [arr[pos + k].astype(np.int64) for k in range(4)]
    rel = bb[0] | (bb[1] << 8) | (bb[2] << 16) | (bb[3] << 24)
    rel = np.where(rel >= 2**31, rel - 2**32, rel)
    va0 = tva + pos
    res = {t: [] for t in targets}
    for k in (0, 1, 2, 4):
        tg = va0 + 4 + k + rel
        for t in targets:
            for j in np.where(tg == t)[0]:
                res[t].append((int(va0[j]) - 2, k))
    return res
if __name__ == '__main__':
    m = MachO(sys.argv[1])
    ts = [int(x, 0) for x in sys.argv[2:]]
    for t, l in xrefs(m, ts).items():
        print(hex(t), [(hex(a), k) for a, k in sorted(l)])
