#!/usr/bin/env python3
"""data_gen.py: DLL の .rdata/.data/_RDATA を wasm linear の 0x30000000+RVA に敷設する C を生成 (m6_data_gen と同じ規約)。
8B 絶対 pointer (.reloc DIR64) は 0x180000000+X → 0x30000000+X に補正。usage: data_gen.py DLL out.c
相対化モード (環境変数 OTT_RELOC=1): 敷設先を (ott_gbase + RVA) にし、DIR64 slot は敷設後に (ott_gbase - 0x30000000) を加算する。
既定 (未設定) の出力は従来と同一。"""
import sys, struct, pefile, json, os
IMG = 0x180000000; BASE = 0x30000000
RELOC = os.environ.get('OTT_RELOC') == '1'
pe = pefile.PE(sys.argv[1])
img = bytearray(pe.get_memory_mapped_image())
# relocs
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
secs = []
for s in pe.sections:
    n = s.Name.rstrip(b'\0').decode()
    if n in ('.rdata', '.data', '_RDATA'):
        secs.append((n, s.VirtualAddress, s.Misc_VirtualSize))
fixed = 0
slots = []
for r in relocs:
    for n, va, vs in secs:
        if va <= r < va + vs - 7:
            v = struct.unpack_from('<Q', img, r)[0]
            if IMG <= v < IMG + 0x308000:
                struct.pack_into('<Q', img, r, v - IMG + BASE); fixed += 1
                slots.append(r)
out = ['#include <stdint.h>\n#include <string.h>\n']
if RELOC:
    out.append('extern uint64_t ott_gbase;\n')
for n, va, vs in secs:
    sym = n.strip('.').lstrip('_')
    data = bytes(img[va:va + vs])
    out.append('static const unsigned char d_%s[] = {\n' % sym + ',\n'.join(','.join('0x%02x' % b for b in data[j:j + 24]) for j in range(0, len(data), 24)) + '\n};\n')
# .text 内の jump table (data in code) / text 参照窓: lift_meta.json から
extra = []
if len(sys.argv) > 3:
    meta = json.load(open(sys.argv[3]))
    wins = [(a - IMG, n) for a, n in meta.get('jt_ranges', [])] + [(a - IMG - 16, 256) for a in meta.get('textrefs', [])]
    for rva, n in sorted(set(wins)):
        extra.append((rva, bytes(img[rva:rva + n])))
for k, (rva, data) in enumerate(extra):
    out.append('static const unsigned char x_%d[] = {%s};\n' % (k, ','.join('0x%02x' % b for b in data)))
out.append('void ott_data_install(void) {\n')
if RELOC:
    for k, (rva, data) in enumerate(extra):
        out.append('  memcpy((void*)(uintptr_t)(ott_gbase + 0x%xu), x_%d, %du);\n' % (rva, k, len(data)))
    for n, va, vs in secs:
        sym = n.strip('.').lstrip('_')
        out.append('  memcpy((void*)(uintptr_t)(ott_gbase + 0x%xu), d_%s, %du);\n' % (va, sym, vs))
    for r in sorted(set(slots)):
        out.append('  *(uint64_t*)(uintptr_t)(ott_gbase + 0x%xu) += ott_gbase - 0x%xull;\n' % (r, BASE))
else:
    for k, (rva, data) in enumerate(extra):
        out.append('  memcpy((void*)0x%xu, x_%d, %du);\n' % (BASE + rva, k, len(data)))
    for n, va, vs in secs:
        sym = n.strip('.').lstrip('_')
        out.append('  memcpy((void*)0x%xu, d_%s, %du);\n' % (BASE + va, sym, vs))
out.append('}\n')
open(sys.argv[2], 'w').write(''.join(out))
print('[data_gen] sections', [(n, hex(va), vs) for n, va, vs in secs], 'reloc fixed', fixed)
