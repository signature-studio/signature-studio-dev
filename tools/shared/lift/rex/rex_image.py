#!/usr/bin/env python3
"""REX Shared Library (block24351_PE.bin) を VA 0x30000000 へ敷設する 2 種のイメージと rex_layout.h を作る (T-SH-44 / #2733)。

- DIR64 再配置を 0x180000000 基準 → 0x30000000 基準に適用する (wasm と native で同一のアドレス)。
- IAT slot: wasm 側は pseudo-VA (IMP_VA_BASE + index)、native 側は 0 (native_ref.c がスタブの関数ポインタを敷設する)。
usage: rex_image.py DLL OUTDIR
出力: image_wasm.bin / image_native.bin (各 SizeOfImage バイト), rex_layout.h
"""
import struct, sys, os
import pefile

BASE = 0x30000000
IMPBASE = 0x1D80000  # fle_cpu.h の IMP_VA_BASE と同一
IMPORTS_NATIVE = {'WaitForSingleObject': 'WAIT', 'ReleaseMutex': 'RELEASE', 'RtlPcToFileHeader': 'RTLPC',
                  'RaiseException': 'RAISE', 'GetLastError': 'GLE'}

pe = pefile.PE(sys.argv[1])
outdir = sys.argv[2]
IMG = pe.OPTIONAL_HEADER.ImageBase
SIZE = pe.OPTIONAL_HEADER.SizeOfImage
img = bytearray(pe.get_memory_mapped_image())
img += bytes(max(0, SIZE - len(img)))
img = img[:SIZE]
delta = IMG - BASE

nrel = 0
rd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
raw = bytes(img[rd.VirtualAddress:rd.VirtualAddress + rd.Size])
i = 0
while i + 8 <= len(raw):
    page, blk = struct.unpack_from('<II', raw, i)
    if blk < 8:
        break
    for k in range((blk - 8) // 2):
        e = struct.unpack_from('<H', raw, i + 8 + 2 * k)[0]
        if (e >> 12) != 10:
            continue
        rva = page + (e & 0xfff)
        v = struct.unpack_from('<Q', img, rva)[0]
        if IMG <= v < IMG + SIZE:
            struct.pack_into('<Q', img, rva, v - delta)
            nrel += 1
    i += blk

slots = {}
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in d.imports:
        if imp.name:
            slots[imp.address - IMG] = imp.name.decode()
order = sorted(slots)
wasm = bytearray(img)
native = bytearray(img)
for idx, slot in enumerate(order):
    struct.pack_into('<Q', wasm, slot, IMPBASE + idx)
    struct.pack_into('<Q', native, slot, 0)
open(os.path.join(outdir, 'image_wasm.bin'), 'wb').write(bytes(wasm))
open(os.path.join(outdir, 'image_native.bin'), 'wb').write(bytes(native))

# DllMain 経路 (lift_x64c.sh dllmain) 用。fle_cpu.c が同名の strong 定義 (imp_*) を持つ import は、
# fle_cpu.c のコンパイル時だけ -D で別名に退け (fle_cpu.c 本体は変えない)、rex 専用の no-op 表を唯一の定義にする。
import re
FLE_CPU = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'flelift', 'rt', 'fle_cpu.c')
defined = set(re.findall(r'^void imp_(\w+)\(void\)', open(FLE_CPU).read(), re.M))
iat_names = set(slots.values())
open(os.path.join(outdir, 'fle_cpu_rename.flags'), 'w').write(
    ' '.join('-Dimp_%s=rexdm_fle_imp_%s' % (n, n) for n in sorted(defined & iat_names)) + '\n')
RGLUE = {'WaitForSingleObject', 'ReleaseMutex', 'RtlPcToFileHeader'}   # rex_glue.c が定義する 3 件
noop = ['/* rex_image.py が生成 (DllMain 経路の no-op import 表。戻り値 0)。 */',
        '#include "fle_cpu.h"', 'void rex_hit(void);']
for n in sorted(iat_names - RGLUE):
    noop.append('void imp_%s(void) { rex_hit(); R[RAX] = 0; R[RSP] += 8; }' % n)
open(os.path.join(outdir, 'rex_imp_noop.c'), 'w').write('\n'.join(noop) + '\n')
open(os.path.join(outdir, 'iat_slots.txt'), 'w').write(''.join('%x %s\n' % (s, slots[s]) for s in order))

exports = {e.name.decode(): e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
data = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.data')
# 0x1380: mov rax,[rip+disp] (7 バイト)。REX の ctx (this) 取得点。次命令 RVA 0x1387 + disp
ctx_rva = 0x1380 + 7 + 0x48a81
assert data.VirtualAddress <= ctx_rva < data.VirtualAddress + data.Misc_VirtualSize
lay = {'base': BASE, 'img_size': SIZE, 'arena': 0x30100000, 'arena_sz': int(os.environ.get('REX_ARENA_SZ', '0x10000'), 0),
       'ctx_rva': ctx_rva, 'data_rva': data.VirtualAddress, 'data_sz': data.Misc_VirtualSize,
       'exp_creator_rva': exports['REXGetCreatorInfo'], 'exp_info_rva': exports['REXGetInfo'],
       'dllmain_rva': pe.OPTIONAL_HEADER.AddressOfEntryPoint, 'iat': {}}
for name, tag in IMPORTS_NATIVE.items():
    rva = [s for s, n in slots.items() if n == name]
    if rva:
        lay['iat'][name] = rva[0]
L = ['#define REX_BASE 0x%xULL' % lay['base'],
     '#define REX_IMG_SIZE 0x%x' % lay['img_size'],
     '#define REX_ARENA 0x%xULL' % lay['arena'],
     '#define REX_ARENA_SZ 0x%x' % lay['arena_sz'],
     '#define REX_CTX_RVA 0x%x' % lay['ctx_rva'],
     '#define REX_DATA_RVA 0x%x' % lay['data_rva'],
     '#define REX_DATA_SZ 0x%x' % lay['data_sz'],
     '#define REX_EXP_CREATOR_RVA 0x%x' % lay['exp_creator_rva'],
     '#define REX_EXP_INFO_RVA 0x%x' % lay['exp_info_rva'],
     '#define REX_DLLMAIN_RVA 0x%x' % lay['dllmain_rva']]
for name, tag in IMPORTS_NATIVE.items():
    if name in lay['iat']:
        L.append('#define REX_IAT_%s_RVA 0x%x' % (tag, lay['iat'][name]))
open(os.path.join(outdir, 'rex_layout.h'), 'w').write('\n'.join(L) + '\n')
import json
json.dump(lay, open(os.path.join(outdir, 'layout.json'), 'w'), indent=1)
print('[rex_image] SizeOfImage=0x%x relocs(DIR64 in range)=%d iat=%d text=0x%x+0x%x data=0x%x+0x%x'
      % (SIZE, nrel, len(order), text.VirtualAddress, text.Misc_VirtualSize, data.VirtualAddress, data.Misc_VirtualSize))
