#!/usr/bin/env python3
"""fle_data_gen.py: FLEngine_x64.dll の image 内容を wasm linear (恒等写像: address = VA) に敷設する C を生成。

敷設方針 (CAB-226):
    - .data (raw 全部), .rdata, .didata, .reloc: 生バイトをコピー。恒等写像ゆえ .reloc の image 内 pointer は補正不要。
    (FLEngine は CPU 特性 flag 等の変数が .reloc 〜 .rdata 直後の領域に置かれているため .reloc も敷設する)
  - .bss: raw 無し (wasm linear 初期値 0 のまま — 追加書込不要)。
  - .idata: 各 IAT slot に pseudo-VA (IMP_VA_BASE + import index) を敷設。
    `mov rax,[iat]; call rax` 形の間接呼出を ott_dispatch の imp 経路に解決させるため。
  - .text: 原則不要 (コードは C 化済み) だが jump table 等「データとして読まれる窓」だけ敷設
    (lift_meta.json の jt_ranges + textrefs)。

usage: fle_data_gen.py PE out.c lift_meta.json [shift]
    shift (省略時 0) は x64c の --shift と同値。VA を wasm 上の番地へ写す (敷設先 = VA - shift)。
"""
import sys, struct, pefile, json

pe = pefile.PE(sys.argv[1])
img = bytearray(pe.get_memory_mapped_image())
IMG = pe.OPTIONAL_HEADER.ImageBase
SHIFT = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0   # x64c --shift と同じ (敷設先 = IMG + RVA - SHIFT)
meta = json.load(open(sys.argv[3]))
impbase = int(meta.get('impbase', 0x1D80000))

# ---- IAT slot → pseudo-VA (lift_meta.iat_map の index 順) ----
iat_writes = []
for k, (slot_hex, ent) in enumerate(sorted(meta.get('iat_map', {}).items())):
    slot = int(slot_hex, 16)
    idx = ent['index']
    struct.pack_into('<Q', img, slot - IMG, impbase + idx)

# ---- 敷設セクション ----
secs = []
for s in pe.sections:
    n = s.Name.rstrip(b'\0').decode()
    if n in ('.data', '.rdata', '.didata', '.reloc'):
        secs.append((n, s.VirtualAddress, s.Misc_VirtualSize, s.SizeOfRawData))

# ---- .text 内データ窓 (jump table / textrefs) ----
wins = []
for a, n in meta.get('jt_ranges', []):
    wins.append((a - IMG, n + 16))
for a in meta.get('textrefs', []):
    wins.append((a - IMG - 16, 96))
# vtable (#1936/#2005): RIP 相対参照が無く jt_ranges にも入らないため、窓を明示的に足す
for a, n in [(0x42f670, 0x30)]:
    if IMG <= a < IMG + pe.OPTIONAL_HEADER.SizeOfImage:   # FLEngine 固有の VA。他の image では範囲外になるので足さない
        wins.append((a - IMG, n))

out = ['#include <stdint.h>\n#include <string.h>\n']
for k, (rva, n) in enumerate(sorted(set(wins))):
    data = bytes(img[rva:rva + n])
    out.append('static const unsigned char w_%d[] = {%s};\n' % (k, ','.join('0x%02x' % b for b in data)))
for n, va, vs, raw in secs:
    data = bytes(img[va:va + min(vs, raw) if raw else vs])
    out.append('static const unsigned char d_%s[] = {\n' % n.strip('.').lstrip('_') +
               ',\n'.join(','.join('0x%02x' % b for b in data[j:j + 24]) for j in range(0, len(data), 24)) + '\n};\n')

out.append('void fle_data_install(void) {\n')
for k, (rva, n) in enumerate(sorted(set(wins))):
    out.append('  memcpy((void*)0x%xu, w_%d, %du);\n' % (IMG + rva - SHIFT, k, n))
for n, va, vs, raw in secs:
    ln = min(vs, raw) if raw else vs
    out.append('  memcpy((void*)0x%xu, d_%s, %du);\n' % (IMG + va - SHIFT, n.strip('.').lstrip('_'), ln))
out.append('}\n')
open(sys.argv[2], 'w').write(''.join(out))
tot = sum(min(vs, raw) if raw else vs for _, _, vs, raw in secs) + sum(n for _, n in set(wins))
print('[fle_data_gen] sections %s, windows %d, total %d bytes, iat slots %d (impbase %#x)' % (
    [(n, hex(va), min(vs, raw) if raw else vs) for n, va, vs, raw in secs], len(set(wins)), tot, len(meta.get('iat_map', {})), impbase))
