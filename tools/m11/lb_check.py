#!/usr/bin/env python3
"""lb_check.py — M11 LB_BASE 適用の静的検査 (#222). m11_image_gen.py と独立 (pefile のメモリマップ像 + DIR64 から再計算).
  usage: lb_check.py PE IMAGE_BIN [LB_BASE=0x10000] [--negative]
  1. image[LB+rva] == PE の KEEP 節 (.text/.data/.rdata/.didata) の生バイト (reloc 8B 以外)
  2. 全 DIR64 reloc 先で: 元の値 v が image 範囲 (IMG,IMG+0x1ac0000) → image 値 == v-IMG+LB かつ >= 0x10000 (lb_layout 相当 assert)
  3. 補正漏れ 0: reloc 外の 8B 整列 qword で image 範囲値のもの = 「非ポインタ lookalike」件数を併記 (補正しない; audit_va.py と同定義)
  4. LB_BASE 未満 (linear < LB) が全 0 (NULL 領域)
  --negative: image を 1 箇所壊して FAIL することを確認 (ネガティブコントロール)
exit 0 = PASS"""
import sys, struct, json
import pefile

args = [a for a in sys.argv[1:] if not a.startswith('--')]
pe_path, img_path = args[0], args[1]
LB = int(args[2], 0) if len(args) > 2 else 0x10000
NEG = '--negative' in sys.argv
KEEP = ('.text', '.data', '.rdata', '.didata')
pe = pefile.PE(pe_path)
IMG = pe.OPTIONAL_HEADER.ImageBase
mm = pe.get_memory_mapped_image()
img = bytearray(open(img_path, 'rb').read())
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
raw = mm[d.VirtualAddress:d.VirtualAddress + d.Size]
relocs = []
i = 0
while i + 8 <= len(raw):
    page, blk = struct.unpack_from('<II', raw, i)
    if blk < 8:
        break
    for k in range((blk - 8) // 2):
        e = struct.unpack_from('<H', raw, i + 8 + 2 * k)[0]
        if (e >> 12) == 10:
            relocs.append(page + (e & 0xfff))
    i += blk
secs = [(s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections]
keep = [(n, va, vs) for (n, va, vs) in secs if n in KEEP]
top = max(va + vs for (n, va, vs) in keep)


def in_keep(r):
    return any(va <= r and r + 8 <= va + vs for (n, va, vs) in keep)


if NEG:
    r0 = next(r for r in relocs if in_keep(r) and IMG < struct.unpack_from('<Q', mm, r)[0] < IMG + 0x1ac0000)
    struct.pack_into('<Q', img, LB + r0, struct.unpack_from('<Q', img, LB + r0)[0] - LB)  # LB 補正 1 件を落とす
res = dict(lb_base=hex(LB), image_bytes=len(img), reloc_total=len(relocs))
errs = []
if len(img) < LB + top:
    errs.append('image が短い: %d < %d' % (len(img), LB + top))
relset = set(relocs)
# 1+4: 非 reloc バイトの一致 / NULL 領域
bad_bytes = 0
reloc_bytes = set()
for r in relocs:
    reloc_bytes.update(range(r, r + 8))
for (n, va, vs) in keep:
    seg = mm[va:va + vs]
    got = img[LB + va:LB + va + vs]
    if len(got) != len(seg):
        errs.append('%s 長さ不一致' % n)
        continue
    if seg == bytes(got):
        continue
    for o in range(len(seg)):
        if seg[o] != got[o] and (va + o) not in reloc_bytes:
            bad_bytes += 1
res['non_reloc_byte_mismatch'] = bad_bytes
res['null_region_nonzero_bytes'] = sum(1 for b in img[:LB] if b)
# 2: reloc 先
n_fix = n_low_before = n_low_after = n_bad = n_ge = 0
for r in relocs:
    if not in_keep(r):
        continue
    v = struct.unpack_from('<Q', mm, r)[0]
    g = struct.unpack_from('<Q', img, LB + r)[0]
    if IMG < v < IMG + 0x1ac0000:
        n_fix += 1
        want = v - IMG + LB
        if g != want:
            n_bad += 1
        if v - IMG < 0x10000:
            n_low_before += 1
        if g < 0x10000:
            n_low_after += 1
        if g >= 0x10000:
            n_ge += 1
    elif g != v:
        n_bad += 1
res.update(dir64_fixed=n_fix, dir64_value_mismatch=n_bad, targets_rva_lt_0x10000_before=n_low_before,
           targets_lvalt_0x10000_after=n_low_after, targets_ge_0x10000_after=n_ge)
# 3: 非ポインタ lookalike (参考)
look = 0
for (n, va, vs) in keep:
    if n not in ('.data', '.rdata'):
        continue
    for o in range(va, va + vs - 7, 8):
        v = struct.unpack_from('<Q', mm, o)[0]
        if IMG <= v < IMG + pe.OPTIONAL_HEADER.SizeOfImage and o not in relset:
            look += 1
res['non_pointer_lookalikes_not_in_reloc(.data/.rdata)'] = look
ok = not errs and bad_bytes == 0 and n_bad == 0 and res['null_region_nonzero_bytes'] == 0 and (n_low_after == 0 if LB >= 0x10000 else True)
res['errors'] = errs
res['verdict'] = 'PASS' if ok else 'FAIL'
print(json.dumps(res, indent=1, ensure_ascii=False))
sys.exit(0 if ok else 1)
