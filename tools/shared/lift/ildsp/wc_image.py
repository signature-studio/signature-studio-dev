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
ARENA_SZ = int(os.environ.get('WC_ARENA_SZ', '0x10000'), 0)  # init (0x1b7d80) の確保が 64 KiB を超えるため PSOLA では 4 MiB (#4302)
ENTRY_RVA = int(os.environ.get('WC_ENTRY_RVA', '0x1ac470'), 0)  # WaveformColouring_CreateInstance (export)
INIT_RVA = int(os.environ.get('WC_INIT_RVA', '0'), 0)  # CreateInstance の前に 1 回呼ぶ host 初期化 (0 = なし)

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
VTABLE_RVA = int(os.environ.get('WC_VTABLE_RVA', '0x3e01b0'), 0)
SLOT_RVA = []
for k in range(6):
    v = struct.unpack_from('<Q', img, VTABLE_RVA + 8 * k)[0]
    assert BASE <= v < BASE + SIZE, hex(v)
    SLOT_RVA.append(v - BASE)
# 差分テストで CreateInstance の直後に呼ぶ slot の数。既定は slot 0 だけ (slot 1 以降は this の内部フィールドに
# host 側の事前設定が要り、既定の入力 (0) では null 参照で落ちる)。WC_CALL_SLOTS=6 は probe_slots.sh が使う (実測は REPORT.md §5-5)。
CALL_SLOTS = int(os.environ.get('WC_CALL_SLOTS', '1'))
# 呼ぶ slot の番号と順序 (既定は 0 から CALL_SLOTS 個)。WC_CALL_IDX="0 4 5" のように指定すると、その順に呼ぶ (lift_psola.sh)。
CALL_IDX = [int(x) for x in os.environ.get('WC_CALL_IDX', ' '.join(str(k) for k in range(CALL_SLOTS))).split()]
CALL_SLOTS = len(CALL_IDX)
CALL_RVA = [SLOT_RVA[k] for k in CALL_IDX]
# 呼出しの引数 (RDX, R8, R9, 5 番目 = 出力)。WC_CALL_ARGS="0 16 IN OUT" のように 4 個指定する (#4302)。
# IN/OUT は psola_init_probe.sh と同じ位置 (+0x8000/+0xC000)。既定 "IN 0 0 0" は従来の差分テストと同じ (RDX=入力・他は 0)。
_CA = {'IN': ARENA + 0x8000, 'OUT': ARENA + 0xC000}
# slot ごとに引数が違う (slot 1: RDX=入力・R8=出力 / slot 3: RDX=0・R8=16・R9=入力・S5=出力) ため、
# WC_CALL_ARGS は呼ぶ slot と同じ数の "RDX R8 R9 S5" 組をセミコロンで区切って指定する。1 組だけなら全 slot 共通。
_ARG_SETS = [s.split() for s in os.environ.get('WC_CALL_ARGS', 'IN 0 0 0').split(';')]
_ARG_SETS = [[_CA.get(t) if t in _CA else int(t, 0) for t in s] for s in _ARG_SETS]
assert all(len(s) == 4 for s in _ARG_SETS), _ARG_SETS
assert len(_ARG_SETS) in (1, CALL_SLOTS), (len(_ARG_SETS), CALL_SLOTS)
CALL_ARGS = _ARG_SETS if len(_ARG_SETS) == CALL_SLOTS else _ARG_SETS * CALL_SLOTS
# 戻り値 rax を acc に畳み込む slot (WC_RET_IDX。既定は呼ぶ全 slot)。戻り値が ABI 上未定義の slot (void 相当) は外す。
RET_IDX = [int(x) for x in os.environ.get('WC_RET_IDX', ' '.join(str(k) for k in CALL_IDX)).split()]
RET_MASK = sum(1 << i for i, k in enumerate(CALL_IDX) if k in RET_IDX)
lay = {'base': BASE, 'img_size': SIZE, 'arena': ARENA, 'arena_sz': ARENA_SZ, 'entry_rva': ENTRY_RVA,
       'data_rva': data.VirtualAddress, 'data_sz': data.Misc_VirtualSize, 'text_rva': text.VirtualAddress,
       'vtable_rva': VTABLE_RVA, 'slots': CALL_RVA, 'call_slots': CALL_SLOTS, 'ret_mask': RET_MASK,
       'init_rva': INIT_RVA, 'call_args': CALL_ARGS,  # slot ごとの [RDX, R8, R9, S5]
       'iat_names': [slots[s] for s in order], 'iat_rva': {slots[s]: s for s in order}}
L = ['#define WC_BASE 0x%xULL' % BASE,
     '#define WC_IMG_SIZE 0x%x' % SIZE,
     '#define WC_ARENA 0x%xULL' % ARENA,
     '#define WC_ARENA_SZ 0x%x' % ARENA_SZ,
     '#define WC_ENTRY_RVA 0x%x' % ENTRY_RVA,
     '#define WC_INIT_RVA 0x%x' % INIT_RVA,
     '#define WC_DATA_RVA 0x%x' % data.VirtualAddress,
     '#define WC_DATA_SZ 0x%x' % data.Misc_VirtualSize,
     '#define WC_CALL_SLOTS %d' % CALL_SLOTS,
     '#define WC_RET_MASK 0x%x' % RET_MASK,
     'static const uint32_t WC_SLOT_RVA[] = {%s};' % ', '.join('0x%x' % s for s in CALL_RVA),
     'static const uint64_t WC_SLOT_ARGS[][4] = {%s};' % ', '.join(
         '{0x%xULL, 0x%xULL, 0x%xULL, 0x%xULL}' % tuple(a) for a in CALL_ARGS)]
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
