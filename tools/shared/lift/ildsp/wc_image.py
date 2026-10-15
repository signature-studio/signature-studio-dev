#!/usr/bin/env python3
"""ildsp (block24360_PE.bin) を VA 0x30000000 へ敷設する 2 種のイメージと wc_layout.h / layout.json を作る (T-SH-52 / #3216)。

rex/rex_image.py と同じ方式: DIR64 再配置を 0x180000000 基準 → 0x30000000 基準に直す。
IAT slot は wasm 側が pseudo-VA (IMP_VA_BASE + index)、native 側は 0 (wc_native_ref.c がスタブを敷設する)。
usage: wc_image.py DLL OUTDIR
出力: image_wasm.bin / image_native.bin (各 SizeOfImage バイト), wc_layout.h, layout.json
"""
import struct, sys, os, json
import pefile

BASE = 0x30000000
IMPBASE = 0x1D80000  # fle_cpu.h の IMP_VA_BASE と同一
ARENA = 0x30500000   # ヒープ (HeapAlloc の bump 領域)。image の外・wasm 線形メモリ内
ARENA_SZ = 0x10000
ENTRY_RVA = 0x1ac470  # WaveformColouring_CreateInstance (export)

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

text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
data = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.data')
iat = {slots[s]: s for s in order}
# vtable (CreateInstance が置く vptr 先) の slot 先。上の DIR64 補正で img の値は既に BASE 基準なので、RVA = v - BASE
VTABLE_RVA = 0x3e01b0
SLOT_RVA = []
for k in range(6):
    v = struct.unpack_from('<Q', img, VTABLE_RVA + 8 * k)[0]
    assert BASE <= v < BASE + SIZE, hex(v)
    SLOT_RVA.append(v - BASE)
# 差分テストで CreateInstance の直後に呼ぶ slot の数。既定は slot 0 だけ (slot 1 以降は this の内部フィールドに
# host 側の事前設定が要り、既定の入力 (0) では null 参照で落ちる)。WC_CALL_SLOTS=6 は probe_slots.sh が使う (実測は REPORT.md §5-5)。
CALL_SLOTS = int(os.environ.get('WC_CALL_SLOTS', '1'))
lay = {'base': BASE, 'img_size': SIZE, 'arena': ARENA, 'arena_sz': ARENA_SZ, 'entry_rva': ENTRY_RVA,
       'data_rva': data.VirtualAddress, 'data_sz': data.Misc_VirtualSize, 'text_rva': text.VirtualAddress,
       'vtable_rva': VTABLE_RVA, 'slots': SLOT_RVA, 'call_slots': CALL_SLOTS,
       'iat_names': [slots[s] for s in order], 'iat_rva': {slots[s]: s for s in order}}
L = ['#define WC_BASE 0x%xULL' % BASE,
     '#define WC_IMG_SIZE 0x%x' % SIZE,
     '#define WC_ARENA 0x%xULL' % ARENA,
     '#define WC_ARENA_SZ 0x%x' % ARENA_SZ,
     '#define WC_ENTRY_RVA 0x%x' % ENTRY_RVA,
     '#define WC_DATA_RVA 0x%x' % data.VirtualAddress,
     '#define WC_DATA_SZ 0x%x' % data.Misc_VirtualSize,
     '#define WC_CALL_SLOTS %d' % CALL_SLOTS,
     'static const uint32_t WC_SLOT_RVA[] = {%s};' % ', '.join('0x%x' % s for s in SLOT_RVA)]
for name in ('HeapAlloc', 'HeapFree', 'GetLastError', 'SetLastError', 'GetCurrentProcess', 'EnterCriticalSection',
             'LeaveCriticalSection', 'FlsGetValue', 'FlsSetValue', 'IsProcessorFeaturePresent', 'RaiseException',
             'RtlCaptureContext', 'RtlLookupFunctionEntry', 'RtlPcToFileHeader', 'RtlVirtualUnwind',
             'SetUnhandledExceptionFilter', 'UnhandledExceptionFilter', 'TerminateProcess'):
    if name in iat:
        L.append('#define WC_IAT_%s_RVA 0x%x' % (name, iat[name]))
open(os.path.join(outdir, 'wc_layout.h'), 'w').write('\n'.join(L) + '\n')
json.dump(lay, open(os.path.join(outdir, 'layout.json'), 'w'), indent=1)
print('[wc_image] SizeOfImage=0x%x relocs(DIR64 in range)=%d iat=%d text=0x%x+0x%x data=0x%x+0x%x'
      % (SIZE, nrel, len(order), text.VirtualAddress, text.Misc_VirtualSize, data.VirtualAddress, data.Misc_VirtualSize))
