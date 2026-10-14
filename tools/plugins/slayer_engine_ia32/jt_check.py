#!/usr/bin/env python3
"""jt_check.py: lift 出力の全 switch (間接 jmp の jump table) の case 値集合が、PE の生データの表と一致するかを検査する (#1098 受入 4)。

  python3 jt_check.py <ott_lifted.c> <lift_meta.json> <block22434_PE.bin>        gate (不一致があれば exit 1)
  python3 jt_check.py <ott_lifted.c> <lift_meta.json> <block22434_PE.bin> neg    ネガコン (表の 1 entry を故意に壊し、FAIL を期待)

表の長さ K は lift_meta.json の jt_ranges (4*(K+1) B) から取る。表の値は PE の生バイト (pefile の rva 変換を使わず、section の raw 位置で読む)。
"""
import json, re, struct, sys
C, META, PEF = sys.argv[1], sys.argv[2], sys.argv[3]
NEG = len(sys.argv) > 4
img = open(PEF, 'rb').read()
e_lfanew = struct.unpack_from('<I', img, 0x3C)[0]
nsec = struct.unpack_from('<H', img, e_lfanew + 6)[0]
opt = e_lfanew + 24
IMG = struct.unpack_from('<I', img, opt + 28)[0]
sec_hdr = opt + struct.unpack_from('<H', img, e_lfanew + 20)[0]
secs = []
for i in range(nsec):
    o = sec_hdr + 40 * i
    vsz, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', img, o + 8)
    secs.append((vaddr, max(vsz, rawsz), rawptr))
def raw_u32(va):
    rva = va - IMG
    for vaddr, sz, rawptr in secs:
        if vaddr <= rva and rva + 4 <= vaddr + sz:
            return struct.unpack_from('<I', img, rawptr + (rva - vaddr))[0]
    raise SystemExit('[jt] FAIL: va 0x%x が section 外' % va)
meta = json.load(open(META))
lens = {a: n for a, n in meta['jt_ranges']}
src = open(C).read()
sws = re.findall(r'switch \(LD32\(\(R\[\d\]\*4 \+ (0x[0-9a-f]+)ULL\)\)\) \{ ((?:case 0x[0-9a-f]+ULL: goto L_[0-9a-f]+; )+)default', src)
if not sws:
    raise SystemExit('[jt] FAIL: switch が見つからない')
bad = 0; ok = 0; n_cases = 0; nsw = 0
for base_s, body in sws:
    base = int(base_s, 16)
    if base not in lens:
        print('[jt] FAIL: switch 表 0x%x が jt_ranges に無い' % base); bad += 1; continue
    K = lens[base] // 4 - 1
    raw = [raw_u32(base + 4 * k) for k in range(K)]
    if NEG and nsw == 0:
        raw[len(raw) // 2] ^= 0x10
    cases = set(int(c, 16) for c in re.findall(r'case (0x[0-9a-f]+)ULL', body))
    nsw += 1; n_cases += len(cases)
    if cases == set(raw):
        ok += 1
    else:
        bad += 1
        print('[jt] MISMATCH table 0x%x: only-in-C %s only-in-PE %s' % (base, sorted(hex(x) for x in cases - set(raw)), sorted(hex(x) for x in set(raw) - cases)))
print('[jt] switch 表 %d 本 (case 値 合計 %d)、生データ一致 %d、不一致 %d' % (nsw, n_cases, ok, bad))
if bad:
    print('[jt] FAIL'); sys.exit(1)
print('[jt] OK: 全 jump table の case 値集合 == PE 生データ (表の長さは lift_meta.jt_ranges)')
