#!/usr/bin/env python3
# bin_table_source.py: FastMM bin 表 (BASE + 16*k) の P 値の由来を PE 上で照合する (#942 受入 1・2)。
# 使い方: python3 tools/m11/ldfix/bin_table_source.py [PE_PATH]
# 各 k の P 値 (m11_image.bin 上の値) について、PE 内に 8 バイト LE の生値が現れる箇所と
# その RVA の section を表示する。P が 0x7a50 のように上位 0x40 を欠く場合は +0x400000 も探す。
import os
import sys
import struct
import pefile

PE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin')
IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'm11_image.bin')
IMG = os.path.normpath(os.environ.get('S4_IMAGE', IMG))
BASE = 16404744
KS = [184, 185, 186, 215, 236]

pe = pefile.PE(PE, fast_load=True)
data = pe.__data__
img = open(IMG, 'rb').read()

def sec_name(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.Name.rstrip(b'\0').decode(errors='replace'), s.VirtualAddress + (off - s.PointerToRawData)
    return None, None

print('PE:', PE)
print('IMG:', IMG)
for k in KS:
    P = struct.unpack_from('<Q', img, BASE + 16 * k + 8)[0]
    F = struct.unpack_from('<Q', img, P + 24)[0] if P + 32 <= len(img) else None
    print('k%d P=0x%x F=%s' % (k, P, ('0x%x' % F) if F is not None else '?'))
    for cand in sorted({P, P + 0x400000}):
        pat = struct.pack('<Q', cand)
        hits = []
        i = data.find(pat)
        while i != -1 and len(hits) < 4:
            name, rva = sec_name(i)
            hits.append('raw=0x%x sec=%s rva=0x%x' % (i, name, rva or 0))
            i = data.find(pat, i + 1)
        print('   値 0x%x の PE 出現: %s' % (cand, '; '.join(hits) or 'なし'))
