#!/usr/bin/env python3
"""lb_data_gen.py — tools/ott/lift/data_gen.py の BASE 引数版. DLL の .rdata/.data/_RDATA/jump-table 窓を LB_BASE+RVA に敷設する C を生成.
8B 絶対 pointer (.reloc DIR64, image 内向き) は 0x180000000+X → LB_BASE+X に補正.
usage: lb_data_gen.py DLL out.c lift_meta.json|- LB_BASE [IMG_SIZE] [--m6]
  --m6: RetDec chain 互換 (.rdata/.data のみ, jump-table 窓なし, 入口名 m6_data_install; tools/m6/m6_data_gen.py の BASE 引数版)"""
import sys, struct, pefile, json
M6 = '--m6' in sys.argv
sys.argv = [a for a in sys.argv if a != '--m6']
dll, outc, metaj = sys.argv[1:4]
BASE = int(sys.argv[4], 0)
pe = pefile.PE(dll)
IMG = pe.OPTIONAL_HEADER.ImageBase
IMG_SIZE = int(sys.argv[5], 0) if len(sys.argv) > 5 else pe.OPTIONAL_HEADER.SizeOfImage
img = bytearray(pe.get_memory_mapped_image())
relocs = []
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
raw = bytes(img[d.VirtualAddress:d.VirtualAddress + d.Size])
i = 0
while i + 8 <= len(raw):
    page, blk = struct.unpack_from('<II', raw, i)
    if blk < 8: break
    for k in range((blk - 8) // 2):
        e = struct.unpack_from('<H', raw, i + 8 + 2 * k)[0]
        if (e >> 12) == 10: relocs.append(page + (e & 0xfff))
    i += blk
secs = [(s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections if s.Name.rstrip(b'\0').decode() in (('.rdata', '.data') if M6 else ('.rdata', '.data', '_RDATA'))]
fixed = 0
for r in relocs:
    for n, va, vs in secs:
        if va <= r < va + vs - 7:
            v = struct.unpack_from('<Q', img, r)[0]
            if IMG <= v < IMG + IMG_SIZE:
                struct.pack_into('<Q', img, r, v - IMG + BASE); fixed += 1
out = ['#include <stdint.h>\n#include <string.h>\n']
for n, va, vs in secs:
    sym = n.strip('.').lstrip('_')
    data = bytes(img[va:va + vs])
    out.append('static const unsigned char d_%s[] = {\n' % sym + ',\n'.join(','.join('0x%02x' % b for b in data[j:j + 24]) for j in range(0, len(data), 24)) + '\n};\n')
extra = []
meta = {} if (M6 or metaj == '-') else json.load(open(metaj))
wins = [(a - IMG, n) for a, n in meta.get('jt_ranges', [])] + [(a - IMG - 16, 96) for a in meta.get('textrefs', [])]
for rva, n in sorted(set(wins)):
    extra.append((rva, bytes(img[rva:rva + n])))
for k, (rva, data) in enumerate(extra):
    out.append('static const unsigned char x_%d[] = {%s};\n' % (k, ','.join('0x%02x' % b for b in data)))
out.append('void %s(void) {\n' % ('m6_data_install' if M6 else 'ott_data_install'))
for k, (rva, data) in enumerate(extra):
    out.append('  memcpy((void*)0x%xu, x_%d, %du);\n' % (BASE + rva, k, len(data)))
for n, va, vs in secs:
    sym = n.strip('.').lstrip('_')
    out.append('  memcpy((void*)0x%xu, d_%s, %du);\n' % (BASE + va, sym, vs))
out.append('}\n')
open(outc, 'w').write(''.join(out))
print('[lb_data_gen] base 0x%x sections %s reloc fixed %d' % (BASE, [(n, hex(va), vs) for n, va, vs in secs], fixed))
