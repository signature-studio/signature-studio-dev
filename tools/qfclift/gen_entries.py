#!/usr/bin/env python3
"""QuickFontCache_x64.dll の .pdata RUNTIME_FUNCTION 開始 VA を roots にした entries JSON を生成する。
usage: gen_entries.py PE out.json  (roots = ImageBase + BeginAddress, .text 内のみ。export は pdata 外でも追加)"""
import sys, json, struct, pefile
pe = pefile.PE(sys.argv[1])
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
lo, hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
roots = set()
for i in range(d.Size // 12):
    b, e, u = struct.unpack_from('<III', img, d.VirtualAddress + 12 * i)
    if lo <= b < hi:
        roots.add(base + b)
n_pdata = len(roots)
for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if lo <= s.address < hi:
        roots.add(base + s.address)
json.dump({'roots': sorted(roots), 'calltgt': []}, open(sys.argv[2], 'w'))
print('[qfc entries] pdata funcs %d, +export-only %d, roots %d' % (n_pdata, len(roots) - n_pdata, len(roots)))
