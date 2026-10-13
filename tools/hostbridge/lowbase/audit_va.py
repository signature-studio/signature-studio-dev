#!/usr/bin/env python3
"""audit_va.py — 「VA 整数」として焼き込まれうる箇所の静的監査 (V-shift の取りこぼし検出).
  1. .rdata/.data/_RDATA 内の 8B-aligned qword で値が image VA 範囲 [IMG, IMG+SizeOfImage) にあるもの全数を数え、.reloc DIR64 に載るもの (= PE ローダも補正する = data_gen が補正する真のポインタ)
     と載らないもの (= ローダも触らない非ポインタ; 例: 0x1_80000029 のような bitfield 対) に分類. 併せて DIR64 reloc 先が image 外を指すもの (補正対象外になる) を数える.
  2. IAT スロット (FirstThunk) が VA でなく hint/name RVA (ILT と同値) を持つこと (= V-shift 非依存) を確認. hint/name RVA は image 範囲に入りうるため VA 判定から除外 (#403)。
  3. 低位 base の制約: LB_BASE >= 0x10000 (shimx の序数判定 <0x10000), 64KiB 境界.
usage: audit_va.py DLL [LB_BASE]    (exit 0 = 補正漏れ候補 0)"""
import sys, struct, pefile, json
dll = sys.argv[1]; base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x10000
pe = pefile.PE(dll); IMG = pe.OPTIONAL_HEADER.ImageBase; SZ = pe.OPTIONAL_HEADER.SizeOfImage
img = pe.get_memory_mapped_image()
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]; raw = img[d.VirtualAddress:d.VirtualAddress + d.Size]
relocs = set(); i = 0
while i + 8 <= len(raw):
    page, blk = struct.unpack_from('<II', raw, i)
    if blk < 8: break
    for k in range((blk - 8) // 2):
        e = struct.unpack_from('<H', raw, i + 8 + 2 * k)[0]
        if (e >> 12) == 10: relocs.add(page + (e & 0xfff))
    i += blk
res = {'image_base': hex(IMG), 'size_of_image': hex(SZ), 'reloc_dir64_total': len(relocs)}
inside = missing = reloc_out = 0; per = {}
for s in pe.sections:
    n = s.Name.rstrip(b'\0').decode()
    if n not in ('.rdata', '.data', '_RDATA'): continue
    va, vs = s.VirtualAddress, s.Misc_VirtualSize
    c_in = c_rel = c_miss = 0
    for o in range(va, va + vs - 7, 8):
        v = struct.unpack_from('<Q', img, o)[0]
        if IMG <= v < IMG + SZ:
            c_in += 1
            if o in relocs: c_rel += 1
            else: c_miss += 1
        elif o in relocs: reloc_out += 1
    per[n] = dict(image_range_qwords=c_in, in_reloc=c_rel, not_in_reloc=c_miss); inside += c_in; missing += c_miss
res['sections'] = per
# IAT
iat = 0; iat_va = 0; iat_hint = 0
if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
    for ent in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in ent.imports:
            rva = imp.address - IMG
            v = struct.unpack_from('<Q', img, rva)[0]
            iat += 1
            if v == imp.hint_name_table_rva: iat_hint += 1
            elif IMG <= v < IMG + SZ: iat_va += 1
res['iat_slots'] = iat; res['iat_slots_holding_hint_name_rva'] = iat_hint; res['iat_slots_holding_image_VA'] = iat_va
res['lb_base_ok'] = (base >= 0x10000 and base % 0x10000 == 0)
res['non_pointer_lookalikes_not_in_reloc'] = missing
res['dir64_targets_outside_image'] = reloc_out
print(json.dumps(res, indent=1))
sys.exit(0 if (reloc_out == 0 and iat_va == 0 and res['lb_base_ok']) else 1)
