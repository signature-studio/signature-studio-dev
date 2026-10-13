#!/usr/bin/env python3
"""fa4_chain_map.py <SlateCore.core_64> <epf_dir> <maptrace.txt> — FA-4: FreshAir チェーン構成 / マクロ→子パラメタ ID 写像の復元と検証。

  1) core の .rsrc `FRAR/DUMP` (FRESH AIR v8) から子 snapin の並び (fourcc / 名前 / file offset) とマクロ名表を抽出し、
     native_ctrl.c の CHAIN 定数 {1,0,1,0,2,0,2,2} (0=comp 1=filter 2=gain) と一致することを確認する。
  2) native_ctrl (FA_MAP_TRACE=1) が記録した 0x180c9d700(child,id,value) 呼出を、factory .epf 8 本の macro 値から
     期待値を計算して突合する (S900.. = .epf をファイル名ソートした順。各 scenario 1 回目の process = 3 呼出)。
       id 0x157 <- powf(M[0x9dc4], 0.62)   id 0x158 <- powf(M[0x9e0c], 0.62)   id 0x15a <- M[0x9e60] (そのまま)
     宛先は全て子リスト entry 0 (= チェーン先頭の Filter)。0.62 は rdata 0x1810cac08 の f32。
  exit 0 = 全 epf で一致。
"""
import glob, math, os, re, struct, sys
import pefile

core, epfdir, trace = sys.argv[1:4]
CHAIN = {b'ifsk': ('filter', 1), b'pcsk': ('comp', 0), b'ngsk': ('gain', 2)}   # LE 読みの 'ksfi'/'kscp'/'ksgn'
NATIVE_CHAIN = [1, 0, 1, 0, 2, 0, 2, 2]

pe = pefile.PE(core)
dump = None
for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
    for e in t.directory.entries:
        if e.name and e.name.decode().strip('"') == 'FRAR/DUMP':
            d = e.directory.entries[0].data.struct
            dump = pe.get_data(d.OffsetToData, d.Size)
assert dump, 'FRAR/DUMP not found'
print('FRAR/DUMP: %d B, preset name = %r' % (len(dump), re.search(rb'FRESH AIR v\d+', dump).group().decode()))

chain = []
for m in re.finditer(rb'(ifsk|pcsk|ngsk)\x05\x08\x01\x00([\x01-\x20])\x00\x00\x00([A-Za-z ]+)', dump):
    kind, idx = CHAIN[m.group(1)]
    assert len(m.group(3)) >= m.group(2)[0]
    chain.append((m.start(), m.group(1)[::-1].decode(), m.group(3)[:m.group(2)[0]].decode(), idx))
print('chain (file offset in DUMP / fourcc / name / type idx):')
for i, (off, fc, nm, ix) in enumerate(chain):
    print('  [%d] +0x%03x %s %-10s type=%d' % (i, off, fc, nm, ix))
types = [c[3] for c in chain]
assert types == NATIVE_CHAIN, ('chain mismatch', types, NATIVE_CHAIN)
cnt = {n: sum(1 for c in chain if c[2] == n) for n in ('Filter', 'Compressor', 'Gain')}
print('chain == native_ctrl.c CHAIN %s ; counts %s' % (NATIVE_CHAIN, cnt))
assert cnt == {'Filter': 2, 'Compressor': 3, 'Gain': 3}

tail = dump[chain[-1][0]:]
names = [m.group(2).decode() for m in re.finditer(rb'([\x03\x04\x07])\x00\x00\x00((?:Main|HF\d|Gain|Trim|Both|Macro \d))', tail)]
print('macro/label strings after chain (DUMP 出現順):', names)

# ---- .epf 駆動 → MAPTRACE 突合 ----
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
def ulp_diff(a, b):
    ia, ib = struct.unpack('<i', struct.pack('<f', a))[0], struct.unpack('<i', struct.pack('<f', b))[0]
    return abs(ia - ib)
epfs = sorted(glob.glob(os.path.join(epfdir, '*.epf')))
tr = {}
for ln in open(trace):
    m = re.match(r'MAPTRACE S(\d+) k=(-?\d+) type=(\S+) id=0x([0-9a-f]+) value=([0-9a-f]{8}) keycnt=(\d+) key0=(\d+)', ln)
    if m:
        s, k, ty, i, v, kc, k0 = m.groups()
        tr.setdefault(int(s), []).append((int(k), ty, int(i, 16), struct.unpack('<f', bytes.fromhex(v)[::-1])[0], int(kc), int(k0)))
EXP = f32(0.62)
bad = 0
print('\n%-20s %8s %8s | %-26s %-26s %-18s' % ('epf', 'mid', 'high', '0x157 got/exp(pow .62)', '0x158 got/exp(pow .62)', '0x15a got'))
for i, f in enumerate(epfs):
    d = open(f, 'rb').read()
    mid, high = struct.unpack_from('<2f', d, 0x10)
    calls = tr.get(900 + i, [])
    first = calls[:3]
    ok = len(calls) == 9 and [c[2] for c in first] == [0x157, 0x158, 0x15a] and all(c[0] == 0 and c[1] == 'filter' and c[4:] == (1, 0) for c in first)
    e157, e158 = f32(math.pow(mid, EXP)), f32(math.pow(high, EXP))
    if ok:
        ok = ulp_diff(first[0][3], e157) <= 2 and ulp_diff(first[1][3], e158) <= 2 and first[2][3] == 0.0
    bad += not ok
    g = [c[3] for c in first] + [float('nan')] * 3
    print('%-20s %8.4f %8.4f | %.7f / %.7f     %.7f / %.7f     %.7f  %s' % (os.path.basename(f)[:-4], mid, high, g[0], e157, g[1], e158, g[2], 'OK' if ok else 'FAIL'))
print('\nRESULT: macro->child map %s (%d/%d epf, calls/scenario=%s)' % ('OK' if bad == 0 else 'FAIL', len(epfs) - bad, len(epfs),
      sorted({len(tr.get(900 + i, [])) for i in range(len(epfs))})))
sys.exit(1 if bad or len(epfs) != 8 else 0)
